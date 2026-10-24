import os
import json
import random
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-this-key")

database_url = os.environ.get("DATABASE_URL", "sqlite:///ai_survey.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
# SQLAlchemy 2.x PostgreSQL driver compatibility for Render URLs
if database_url.startswith("postgresql://") and "+psycopg" not in database_url:
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Survey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    interview_type = db.Column(db.String(30), nullable=False, default="Structured")
    interview_mode = db.Column(db.String(30), nullable=False, default="Individual")
    language = db.Column(db.String(40), nullable=False, default="English")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    questions = db.relationship("Question", backref="survey", cascade="all, delete-orphan",
                                order_by="Question.position")
    responses = db.relationship("Response", backref="survey", cascade="all, delete-orphan")


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    survey_id = db.Column(db.Integer, db.ForeignKey("survey.id"), nullable=False)
    text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(30), nullable=False, default="text")
    category = db.Column(db.String(80), default="General")
    position = db.Column(db.Integer, default=1)


class Response(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    survey_id = db.Column(db.Integer, db.ForeignKey("survey.id"), nullable=False)
    respondent_name = db.Column(db.String(120), default="Anonymous")
    respondent_group = db.Column(db.String(120), default="")
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    answers = db.relationship("Answer", backref="response", cascade="all, delete-orphan")


class Answer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    response_id = db.Column(db.Integer, db.ForeignKey("response.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("question.id"), nullable=False)
    answer_text = db.Column(db.Text, default="")
    question = db.relationship("Question")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or len(password) < 8:
            flash("Enter your name, a valid email, and a password of at least 8 characters.", "danger")
            return render_template("register.html")
        if User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "danger")
            return render_template("register.html")
        user = User(name=name, email=email, password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        session["user_id"] = user.id
        session["user_name"] = user.name
        flash("Account created. Welcome!", "success")
        return redirect(url_for("dashboard"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            session.clear()
            session["user_id"] = user.id
            session["user_name"] = user.name
            return redirect(url_for("dashboard"))
        flash("Incorrect email or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    surveys = Survey.query.filter_by(owner_id=session["user_id"]).order_by(Survey.created_at.desc()).all()
    survey_ids = [s.id for s in surveys]
    response_count = Response.query.filter(Response.survey_id.in_(survey_ids)).count() if survey_ids else 0
    question_count = Question.query.join(Survey).filter(Survey.owner_id == session["user_id"]).count()
    return render_template("dashboard.html", surveys=surveys, response_count=response_count,
                           question_count=question_count)


@app.route("/surveys/new", methods=["GET", "POST"])
@login_required
def create_survey():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        interview_type = request.form.get("interview_type", "Structured")
        interview_mode = request.form.get("interview_mode", "Individual")
        language = request.form.get("language", "English")
        raw_questions = request.form.get("questions", "")
        questions = [line.strip() for line in raw_questions.splitlines() if line.strip()]
        if not title:
            flash("Survey title is required.", "danger")
            return render_template("create_survey.html")
        if not questions:
            flash("Add at least one question.", "danger")
            return render_template("create_survey.html")
        if len(questions) > 50:
            flash("A survey can contain up to 50 questions.", "danger")
            return render_template("create_survey.html")
        survey = Survey(title=title, description=description, interview_type=interview_type,
                        interview_mode=interview_mode, language=language, owner_id=session["user_id"])
        db.session.add(survey)
        db.session.flush()
        for i, text in enumerate(questions, start=1):
            db.session.add(Question(survey_id=survey.id, text=text, position=i))
        db.session.commit()
        flash("Survey created successfully.", "success")
        return redirect(url_for("survey_detail", survey_id=survey.id))
    return render_template("create_survey.html")


@app.route("/surveys/<int:survey_id>")
@login_required
def survey_detail(survey_id):
    survey = Survey.query.filter_by(id=survey_id, owner_id=session["user_id"]).first_or_404()
    return render_template("survey_detail.html", survey=survey)


@app.route("/surveys/<int:survey_id>/take", methods=["GET", "POST"])
def take_survey(survey_id):
    survey = Survey.query.get_or_404(survey_id)
    if request.method == "POST":
        respondent_name = request.form.get("respondent_name", "").strip() or "Anonymous"
        respondent_group = request.form.get("respondent_group", "").strip()
        response = Response(survey_id=survey.id, respondent_name=respondent_name,
                            respondent_group=respondent_group)
        db.session.add(response)
        db.session.flush()
        for question in survey.questions:
            answer_text = request.form.get(f"question_{question.id}", "").strip()
            db.session.add(Answer(response_id=response.id, question_id=question.id,
                                  answer_text=answer_text))
        db.session.commit()
        return render_template("thank_you.html", survey=survey)
    return render_template("take_survey.html", survey=survey)


@app.route("/surveys/<int:survey_id>/analytics")
@login_required
def analytics(survey_id):
    survey = Survey.query.filter_by(id=survey_id, owner_id=session["user_id"]).first_or_404()
    responses = Response.query.filter_by(survey_id=survey.id).order_by(Response.submitted_at.desc()).all()
    summaries = []
    for question in survey.questions:
        answers = Answer.query.join(Response).filter(
            Response.survey_id == survey.id, Answer.question_id == question.id
        ).all()
        nonempty = [a.answer_text for a in answers if a.answer_text]
        numeric = []
        for answer in nonempty:
            try:
                n = int(answer)
                if 1 <= n <= 7:
                    numeric.append(n)
            except ValueError:
                pass
        summaries.append({"question": question, "count": len(nonempty),
                          "average": round(sum(numeric) / len(numeric), 2) if numeric else None,
                          "answers": nonempty[:8]})
    return render_template("analytics.html", survey=survey, responses=responses, summaries=summaries)


@app.route("/surveys/<int:survey_id>/delete", methods=["POST"])
@login_required
def delete_survey(survey_id):
    survey = Survey.query.filter_by(id=survey_id, owner_id=session["user_id"]).first_or_404()
    db.session.delete(survey)
    db.session.commit()
    flash("Survey deleted.", "info")
    return redirect(url_for("dashboard"))


@app.route("/health")
def health():
    return {"status": "ok"}


with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host="0.0.0.0",
            port=int(os.environ.get("PORT", "5000")))
