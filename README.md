# Job Application Automation (Django)

An AI-powered job application suite completely rebuilt on the **Django** framework. It helps you seamlessly track job applications, discover new positions, automatically extract job details via AI, and generate personalized cover letters—all from a web dashboard or directly via Telegram.

## ✨ Key Features

- **Web Dashboard**: A centralized UI to view all applications, update statuses, and add new jobs.
- **Telegram Bot Integration**: Automate your application process on the go. Send a job URL to the bot, and it will fetch the description, extract details, and generate an email preview for you to send or save.
- **AI-Powered Generation**: Uses Gemini (or Grok) to read job descriptions and craft high-quality, personalized email outreach based on your CV profile.
- **Job Discovery**: Integrated search for Indeed, Google Jobs, and LinkedIn based on your keywords and location.
- **SQLite Database**: Fully managed via Django ORM (`db.sqlite3`).

---

## 🛠️ Quick Start

### 1. Install Dependencies
Ensure you have Python 3.9+ installed.
```bash
python -m venv .venv

# On Windows:
.\.venv\Scripts\Activate.ps1
# On macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configuration
Copy the `.env.example` to `.env` and fill out your credentials.
```bash
cp .env.example .env
```
Key variables to define:
- **AI Provider**: `AI_PROVIDER` (gemini or grok), `GEMINI_API_KEY`
- **Email Settings**: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`
- **Telegram**: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_CHAT_IDS`
- **Your CV**: Update the path to your PDF resume via `CV_PATH`.

### 3. Database Setup
Run the Django migrations to set up the SQLite database:
```bash
python manage.py makemigrations
python manage.py migrate
```

### 4. Running the Web Dashboard
Launch the Django development server:
```bash
python manage.py runserver
```
Visit `http://localhost:8000/` to view your application tracker.

### 5. Running the Telegram Bot
In a separate terminal (with the virtual environment activated), start the Telegram polling bot:
```bash
python manage.py runbot
```

---

## 📱 Telegram Bot Commands

Once your bot is running, you can interact with it on Telegram.
- **Just paste a job URL** to automatically extract the job description, generate the email, and process your application.
- `/start` — Welcome and instructions
- `/list [n]` — View the latest applications
- `/status <company>` — Search applications by company name
- `/add` — Manually add a job description without a URL
- `/search <keywords>` — Run discovery for new jobs matching your `.env` keywords
- `/update <id> <status>` — Update a job status (e.g., `applied`, `interview`, `offer`)
- `/stats` — View your overall application statistics

---

## 📂 Project Structure

```text
job-application-automation/
├── manage.py             ← Django management script
├── db.sqlite3            ← SQLite database (auto-created after migrations)
├── jobtracker/           ← Django core configuration (settings, urls, wsgi)
├── core/                 ← Business logic & Database Models
│   ├── models.py         ← JobApplication schema
│   └── management/commands/
│       └── runbot.py     ← Telegram bot entry point
├── dashboard/            ← Web Interface (views, urls)
│   ├── views.py          ← UI logic
│   └── templates/        ← HTML pages (dashboard, add_job, discovery)
├── services/             ← External Integrations
│   ├── ai_generator.py   ← Interaction with Gemini/Grok API
│   ├── email_sender.py   ← SMTP mailer
│   └── job_discovery.py  ← Web scraping for job boards 
├── .env                  ← Local environment variables (do not commit)
└── README.md             ← This documentation
```

---

## 🛡️ Privacy & Security
- **Never commit your `.env` file** or database files (`db.sqlite3`). Ensure `.gitignore` is properly configured.
- **Authorization**: The Telegram bot utilizes `TELEGRAM_ALLOWED_CHAT_IDS` so only authorized users can instruct the bot to query the AI or send emails on your behalf.