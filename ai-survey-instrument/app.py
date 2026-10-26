import os
import json
import random
import time
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



def generate_with_model_fallback(client, prompt):
    """Try configured Gemini models in order, falling back on temporary service errors."""
    models = [
        os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
        os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash"),
        os.environ.get("GEMINI_FALLBACK_MODEL_2", "gemini-3.5-flash-lite"),
    ]
    # Preserve order while avoiding duplicate model names.
    models = list(dict.fromkeys(model.strip() for model in models if model and model.strip()))
    last_error = None

    for model in models:
        # Retry one time for transient overload/server errors, then try the next model.
        for attempt in range(2):
            try:
                app.logger.info("Requesting Gemini response with model %s (attempt %s)", model, attempt + 1)
                return client.models.generate_content(model=model, contents=prompt)
            except Exception as exc:
                last_error = exc
                status_code = getattr(exc, "status_code", None)
                error_text = str(exc).lower()
                transient = (
                    status_code in (429, 500, 502, 503, 504)
                    or any(token in error_text for token in (
                        "503", "unavailable", "high demand", "resource_exhausted",
                        "rate limit", "429", "internal server error", "502", "504"
                    ))
                )
                if not transient:
                    raise
                app.logger.warning("Gemini model %s temporarily failed: %s", model, exc)
                if attempt == 0:
                    time.sleep(1)

    if last_error:
        raise last_error
    raise RuntimeError("No Gemini model is configured.")


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



@app.route("/reports")
@login_required
def reports():
    title_filter = request.args.get("title", "").strip()[:200]
    group_filter = request.args.get("group", "").strip()[:120]
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()
    survey_query = Survey.query.filter_by(owner_id=session["user_id"])
    if title_filter:
        survey_query = survey_query.filter(Survey.title.ilike("%" + title_filter + "%"))
    surveys = survey_query.order_by(Survey.created_at.desc()).all()
    survey_ids = [survey.id for survey in surveys]
    response_query = Response.query.filter(Response.survey_id.in_(survey_ids)) if survey_ids else Response.query.filter(False)
    if group_filter:
        response_query = response_query.filter(Response.respondent_group.ilike("%" + group_filter + "%"))
    try:
        if start_date:
            response_query = response_query.filter(Response.submitted_at >= datetime.strptime(start_date, "%Y-%m-%d"))
        if end_date:
            from datetime import timedelta
            response_query = response_query.filter(Response.submitted_at < datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1))
    except ValueError:
        flash("Please enter valid date filters.", "warning")
    responses = response_query.order_by(Response.submitted_at.desc()).all()
    summaries = []
    for survey in surveys:
        matching = [response for response in responses if response.survey_id == survey.id]
        summaries.append({"survey": survey, "questions": len(survey.questions),
            "responses": len(matching), "latest_response": max((r.submitted_at for r in matching), default=None)})
    if request.args.get("export") == "csv":
        import csv, io
        from flask import make_response
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Survey", "Interview Type", "Mode", "Language", "Respondent", "Group", "Submitted At", "Question", "Answer"])
        for response in responses:
            for answer in response.answers:
                writer.writerow([response.survey.title, response.survey.interview_type, response.survey.interview_mode,
                    response.survey.language, response.respondent_name, response.respondent_group,
                    response.submitted_at.strftime("%Y-%m-%d %H:%M:%S") if response.submitted_at else "",
                    answer.question.text if answer.question else "", answer.answer_text])
        result = make_response("\\ufeff" + output.getvalue())
        result.headers["Content-Type"] = "text/csv; charset=utf-8"
        result.headers["Content-Disposition"] = "attachment; filename=fliflafloo-report.csv"
        return result
    return render_template("reports.html", survey_summaries=summaries, total_surveys=len(surveys),
        total_responses=len(responses), total_questions=sum(len(s.questions) for s in surveys),
        title_filter=title_filter, group_filter=group_filter, start_date=start_date, end_date=end_date)

@app.route("/surveys/<int:survey_id>/analytics")
@login_required
def analytics(survey_id):
    survey = Survey.query.filter_by(id=survey_id, owner_id=session["user_id"]).first_or_404()
    responses = Response.query.filter_by(survey_id=survey.id).order_by(Response.submitted_at.desc()).all()
    summaries = []
    all_text = []
    positive_words = {"good", "great", "excellent", "easy", "helpful", "satisfied", "love", "useful", "fast", "clear", "happy", "improve", "improved", "convenient", "friendly", "maayos", "maganda", "mabuti", "madali", "masaya"}
    negative_words = {"bad", "poor", "difficult", "hard", "slow", "confusing", "problem", "issue", "delay", "delayed", "unsatisfied", "hate", "broken", "worse", "frustrating", "mahirap", "pangit", "mabagal", "problema", "malungkot"}
    stop_words = {"the", "and", "for", "that", "this", "with", "you", "your", "are", "was", "were", "have", "has", "had", "from", "but", "not", "what", "when", "where", "how", "why", "can", "could", "would", "should", "will", "about", "into", "their", "there", "they", "them", "then", "than", "very", "just", "also", "our", "its", "it", "a", "an", "to", "of", "in", "on", "is", "i", "my", "we", "me", "be", "as", "at", "or", "if", "so", "do"}
    import re
    for question in survey.questions:
        answers = Answer.query.join(Response).filter(
            Response.survey_id == survey.id, Answer.question_id == question.id
        ).all()
        nonempty = [a.answer_text.strip() for a in answers if a.answer_text and a.answer_text.strip()]
        numeric = []
        for answer in nonempty:
            try:
                n = float(answer)
                if 1 <= n <= 7:
                    numeric.append(n)
            except ValueError:
                pass
        summaries.append({"question": question, "count": len(nonempty),
                          "average": round(sum(numeric) / len(numeric), 2) if numeric else None,
                          "answers": nonempty[:8]})
        if question.question_type.lower() not in ("likert", "rating", "scale", "number"):
            all_text.extend(nonempty)
    sentiment = {"positive": 0, "neutral": 0, "negative": 0}
    word_counts = {}
    for answer in all_text:
        words = re.findall(r"[a-zA-ZÀ-ÿ']+", answer.lower())
        positive = sum(word in positive_words for word in words)
        negative = sum(word in negative_words for word in words)
        sentiment["positive" if positive > negative else "negative" if negative > positive else "neutral"] += 1
        for word in words:
            if len(word) > 2 and word not in stop_words and word not in positive_words and word not in negative_words:
                word_counts[word] = word_counts.get(word, 0) + 1
    top_keywords = sorted(word_counts.items(), key=lambda item: (-item[1], item[0]))[:10]
    return render_template("analytics.html", survey=survey, responses=responses, summaries=summaries,
                           sentiment=sentiment, top_keywords=top_keywords, text_answer_count=len(all_text))


@app.route("/surveys/<int:survey_id>/delete", methods=["POST"])
@login_required
def delete_survey(survey_id):
    survey = Survey.query.filter_by(id=survey_id, owner_id=session["user_id"]).first_or_404()
    db.session.delete(survey)
    db.session.commit()
    flash("Survey deleted.", "info")
    return redirect(url_for("dashboard"))


@app.route("/api/generate-questions", methods=["POST"])
@login_required
def generate_questions():
    """Generate survey/interview questions from the user's selected options."""
    if not os.environ.get("GEMINI_API_KEY"):
        return {"error": "AI question generation is not configured. Add GEMINI_API_KEY in Render Environment settings."}, 503

    payload = request.get_json(silent=True) or {}
    title = str(payload.get("title", "")).strip()[:200]
    description = str(payload.get("description", "")).strip()[:1200]
    interview_type = str(payload.get("interview_type", "Structured")).strip()
    question_style = str(payload.get("question_style", "Mixed")).strip()
    language = str(payload.get("language", "English")).strip()
    audience = str(payload.get("audience", "")).strip()[:300]
    focus = str(payload.get("focus", "")).strip()[:500]
    try:
        count = max(1, min(50, int(payload.get("count", 10))))
    except (TypeError, ValueError):
        count = 10

    allowed_types = {"Structured", "Semi-Structured", "Unstructured"}
    allowed_styles = {"Open-ended", "Likert scale", "Multiple choice", "Mixed"}
    allowed_languages = {"English", "Filipino / Tagalog", "Cebuano", "Ilocano", "Hiligaynon"}
    if interview_type not in allowed_types:
        interview_type = "Structured"
    if question_style not in allowed_styles:
        question_style = "Mixed"
    if language not in allowed_languages:
        language = "English"
    if not title:
        return {"error": "Enter a survey title first so the AI can make relevant questions."}, 400

    type_guidance = {
        "Structured": "Use clear, standardized questions in a consistent order. Keep questions specific and easy to answer.",
        "Semi-Structured": "Provide a mix of planned core questions and flexible follow-up probes. Mark optional follow-up prompts with 'Follow-up:'.",
        "Unstructured": "Use broad, open conversation prompts that invite detailed stories and exploration rather than rigid wording."
    }
    style_guidance = {
        "Open-ended": "Every item should invite a written or spoken answer; avoid yes/no-only questions.",
        "Likert scale": "Write statements suitable for a 5-point agreement scale. Prefix each statement with '[Likert 1-5]' and do not include the scale labels in the statement.",
        "Multiple choice": "For each question, put answer options on the same line separated by ' | '. Include balanced options and an 'Other' option when appropriate.",
        "Mixed": "Create a balanced mix of open-ended questions, Likert statements prefixed '[Likert 1-5]', and multiple-choice questions with options separated by ' | '."
    }
    prompt = (
        "You are an expert research-methods assistant. Generate exactly " + str(count) +
        " useful, ethical, unbiased survey/interview questions.\n"
        "Survey title: " + title + "\n"
        "Purpose/description: " + (description or "Not provided") + "\n"
        "Interview type: " + interview_type + ". " + type_guidance[interview_type] + "\n"
        "Requested question format: " + question_style + ". " + style_guidance[question_style] + "\n"
        "Language: Write every question and answer option in " + language + ".\n"
        "Target respondents: " + (audience or "Not specified") + "\n"
        "Focus areas: " + (focus or "Choose relevant themes based on the survey title and purpose") + "\n\n"
        "Rules: Avoid leading, double-barrelled, repetitive, or overly personal questions. "
        "Number each question. Return only the numbered questions, one per line. "
        "Do not add an introduction, conclusion, or markdown code fence."
    )
    try:
        from google import genai
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        result = generate_with_model_fallback(client, prompt)
        generated = (getattr(result, "text", None) or "").strip()
        questions = []
        for line in generated.splitlines():
            cleaned = line.strip()
            cleaned = __import__("re").sub(r"^\s*(?:\d+[.)]|[-*•])\s*", "", cleaned).strip()
            if cleaned:
                questions.append(cleaned)
        questions = questions[:count]
        if not questions:
            return {"error": "The AI did not return usable questions. Please try again."}, 502
        return {"questions": questions, "count": len(questions)}
    except Exception as exc:
        # Log technical details on the server only; never send API credentials to the browser.
        app.logger.exception("AI question generation failed")
        error_text = str(exc).lower()
        if "api_key_invalid" in error_text or "invalid api key" in error_text or "unauthorized" in error_text or "permission denied" in error_text:
            message = "Gemini rejected the API key or the project does not have access. Check GEMINI_API_KEY in Render."
        elif "429" in error_text or "resource_exhausted" in error_text or "quota" in error_text or "rate limit" in error_text:
            message = "Gemini free-tier quota or rate limit reached. Wait and retry, or check your Google AI Studio quota."
        elif "404" in error_text or "not found" in error_text:
            message = "The selected Gemini model was not found or is unavailable to this API key. Check GEMINI_MODEL."
        elif "timeout" in error_text or "deadline" in error_text:
            message = "The request to Gemini timed out. Please retry with fewer questions."
        elif "503" in error_text or "unavailable" in error_text or "high demand" in error_text:
            message = "Gemini is temporarily busy. The system tried the configured fallback models, but they are also unavailable. Please wait a minute and try again."
        else:
            message = "Gemini request failed after trying the configured models. Check Render Logs and verify your model settings."
        return {"error": message}, 502


@app.route("/api/chat", methods=["POST"])
@login_required
def ai_chat():
    """AI helper for survey creation, question writing, and interpreting survey analytics."""
    if not os.environ.get("GEMINI_API_KEY"):
        return {"error": "The AI chatbot is not configured yet. Add GEMINI_API_KEY in Render Environment settings."}, 503

    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    history = payload.get("history", [])

    if not message:
        return {"error": "Please type a message."}, 400
    if len(message) > 2000:
        return {"error": "Please keep each message under 2,000 characters."}, 400
    if not isinstance(history, list):
        history = []
    # Keep a small, bounded context and accept only simple user/assistant text turns.
    safe_history = []
    for item in history[-8:]:
        if isinstance(item, dict) and item.get("role") in ("user", "assistant"):
            content = str(item.get("content", "")).strip()[:1500]
            if content:
                safe_history.append(f"{item['role'].capitalize()}: {content}")

    prompt = (
        "You are SurveyMate, the helpful AI assistant inside the AI Survey Instrument web app. "
        "Help users create clear, unbiased survey and interview questions, choose structured, "
        "semi-structured, or unstructured formats, understand Likert scales, improve survey design, "
        "and interpret survey analytics. You can answer in English or Filipino/Tagalog when asked. "
        "Use simple wording for students. Do not claim to access private survey records unless the "
        "user includes the relevant data in the chat. Never ask users to share passwords, API keys, "
        "or sensitive personal information. Keep answers practical and concise.\n\n"
        + ("Recent conversation:\n" + "\n".join(safe_history) + "\n\n" if safe_history else "")
        + "User: " + message
    )

    try:
        from google import genai
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        result = generate_with_model_fallback(client, prompt)
        answer = (getattr(result, "text", None) or "").strip()
        if not answer:
            return {"error": "The AI returned an empty response. Please try again."}, 502
        return {"reply": answer}
    except Exception as exc:
        app.logger.exception("AI chatbot request failed")
        error_text = str(exc).lower()
        if "503" in error_text or "unavailable" in error_text or "high demand" in error_text:
            message = "Gemini is temporarily busy. The system tried the configured fallback models, but they are also unavailable. Please wait a minute and try again."
        elif "429" in error_text or "resource_exhausted" in error_text or "quota" in error_text or "rate limit" in error_text:
            message = "Gemini's rate limit or quota was reached across the configured models. Please wait and try again."
        else:
            message = "The AI service failed after trying the configured models. Check Render Logs and verify your model settings."
        return {"error": message}, 502


@app.route("/health")
def health():
    return {"status": "ok"}


with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host="0.0.0.0",
            port=int(os.environ.get("PORT", "5000")))
