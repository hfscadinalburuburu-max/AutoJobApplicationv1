# Job Application Automation System

> AI-powered cold-outreach emailer — reads job listings from CSV, generates personalised emails with Gemini/Grok, and delivers them via SMTP with full logging and rate limiting.

---

## Quick Start

```powershell
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1       # Windows
# source .venv/bin/activate       # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure secrets
cp .env.example .env
# Open .env and fill in: GEMINI_API_KEY, SMTP_USER, SMTP_PASSWORD, SENDER_NAME, PROFILE_SUMMARY

# 4. Add your CV
# Place your resume at the project root as: cv.pdf

# 5. Populate jobs
# Edit jobs.csv with real companies, positions, recruiter emails, and job descriptions

# 6. Dry-run (safe — no emails sent)
python job_applier.py --dry-run

# 7. Live send (set DRY_RUN=false in .env first)
python job_applier.py
```

---

## Project Structure

```
job-application-automation/
├── job_applier.py      # Main orchestrator (entry point)
├── config.py           # Settings loader (reads .env)
├── ai_generator.py     # Gemini / Grok email body generation
├── email_sender.py     # SMTP + MIME builder + CV attachment
├── utils.py            # Logging, CSV helpers, cost estimator
├── jobs.csv            # Input: one row per job to apply to
├── cv.pdf              # Your resume (add this yourself)
├── .env.example        # Secret template — copy to .env
├── requirements.txt    # Python dependencies
└── sent_log.csv        # Auto-created: tracks every send attempt
```

---

## jobs.csv Columns

| Column | Required | Description |
|---|---|---|
| `company_name` | ✅ | Company name |
| `position` | ✅ | Job title |
| `recruiter_email` | ✅ | Recipient email |
| `intro_name` | ✅ | First name for "Dear Alex," greeting |
| `job_description` | ✅ | Full JD text (paste from job board) |
| `custom_note` | ➖ | Extra context to weave into the email |
| `cv_path` | ➖ | Override CV file (e.g. `cv_tailored.pdf`) |

---

## CLI Options

```
python job_applier.py [OPTIONS]

Options:
  --dry-run        Compose & log emails but do NOT send
  --limit N        Only process first N rows
  --company NAME   Filter to rows matching company name
  --help           Show usage
```

---

## Module Self-Tests

```powershell
# Test AI generation (prints one sample email body)
python ai_generator.py

# Test email builder (prints MIME headers, no send)
python email_sender.py

# Validate config (will raise if .env is misconfigured)
python -c "import config; print('Config OK')"
```

---

## Security Notes

- **Never commit `.env`** — it is in `.gitignore`.
- Use a **Gmail App Password**, not your main account password.
- `DRY_RUN=true` is the safe default — flip to `false` only for live sends.
- The `sent_log.csv` and `logs/` directory are also gitignored.

---

## Generating an SBOM

```powershell
cyclonedx-py environment -o sbom.json --format json
```

---

## Extending the System

| Feature | Where to add |
|---|---|
| AI-tailored CV per job | `ai_generator.py` + new `cv_tailorer.py` |
| Follow-up email scheduling | `job_applier.py` — add follow_up_date to log |
| Web review dashboard | New `dashboard.py` (FastAPI) reading `sent_log.csv` |
| LinkedIn scraping | New `scraper.py` populating `jobs.csv` |
| SendGrid instead of SMTP | `email_sender.py` — swap `smtplib` for `sendgrid` SDK |
