# AI Survey Instrument

A starter Flask web app for creating surveys and collecting responses.

## Included in this first version
- User registration, login, and logout
- Dashboard with survey, question, and response counts
- Survey creation with up to 50 questions
- Structured, semi-structured, and unstructured survey type labels
- Individual, group, and random interview mode labels
- Public respondent survey link
- Response storage
- Basic analytics and Likert-style numeric averages
- SQLite locally; PostgreSQL when `DATABASE_URL` is configured
- Render deployment blueprint

## Run locally (Windows / VS Code / PyCharm)

1. Install Python 3.11 or 3.12.
2. Open a terminal in this folder.
3. Create a virtual environment:

   ```powershell
   py -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

4. Install packages:

   ```powershell
   pip install -r requirements.txt
   ```

5. Run:

   ```powershell
   python app.py
   ```

6. Visit http://127.0.0.1:5000 and register an account.

If PowerShell blocks activation, use `.venv\Scripts\python.exe -m pip install -r requirements.txt` and `.venv\Scripts\python.exe app.py`.

## Publish to GitHub

Create an empty repository on GitHub, then run these commands from this folder (replace the URL with your repository URL):

```bash
git init
git add .
git commit -m "Initial AI Survey Instrument app"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
git push -u origin main
```

Do not commit `.env` files, passwords, or API keys.

## Deploy to Render

1. Push this project to GitHub.
2. In Render, choose **New + → Blueprint** and connect the repository.
3. Render reads `render.yaml` and offers to create the web service and PostgreSQL database.
4. Review the resources and deploy.
5. Open the service URL when deployment finishes.

Render plan availability and free-resource policies can change. If the selected database plan is unavailable, create a PostgreSQL database on a plan available to your account and set the web service's `DATABASE_URL` environment variable to its internal connection string.

## Important limitations in this starter
This is the foundation, not the final implementation of every requested feature. AI generation, real translation, audio/video recording, PDF/Word/Excel exports, advanced sentiment analysis, and secure offline sync are not implemented yet. They should be added as separate tested modules. Do not collect sensitive respondent information until access controls, consent, retention, and privacy notices have been reviewed.


## AI chatbot (SurveyMate)

The signed-in app includes a floating AI chatbot for survey design help. It uses Google's Gemini API through the Python backend; the API key is never sent to the browser or committed to GitHub.

### Set up a free Gemini API key

1. Open [Google AI Studio API keys](https://aistudio.google.com/app/apikey) and sign in.
2. Create an API key using a **Free Tier** project, if available to your account.
3. In the Render dashboard, open the `ai-survey-instrument` web service → **Environment**.
4. Add `GEMINI_API_KEY` and paste your own key as its value. Keep it private.
5. Confirm `GEMINI_MODEL` is set to `gemini-2.5-flash` (or change it to a model currently enabled for your free tier), then save and redeploy.
6. For local testing, put `GEMINI_API_KEY=your-key-here` in your local `.env` file. Never commit `.env`.

The Gemini API free tier has model-specific rate limits and availability; it is not unlimited. Review [Google's current billing and free-tier rules](https://ai.google.dev/gemini-api/docs/billing). Do not add billing if you want to remain on the free tier. API provider limits can change.

The chatbot is a general helper and does not automatically read private survey responses or analytics. It only receives the current message and a short recent chat history.
