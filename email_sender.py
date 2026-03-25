"""
email_sender.py — SMTP email construction and delivery.

Builds MIMEMultipart messages with:
  - Plain-text body (greeting + AI content + sign-off)
  - HTML alternative (styled version of the same content)
  - PDF CV attachment

Respects DRY_RUN: when True, returns the built message without sending.
"""
from __future__ import annotations

import logging
import mimetypes
import smtplib
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path
from textwrap import dedent

import config

logger = logging.getLogger("job_applier")

# ── Sign-off block ────────────────────────────────────────────────────────────

def _build_signoff() -> str:
    lines = [
        f"\nBest regards,",
        config.SENDER_NAME,
    ]
    if config.SENDER_PHONE:
        lines.append(config.SENDER_PHONE)
    if config.SENDER_EMAIL:
        lines.append(config.SENDER_EMAIL)
    if config.SENDER_LINKEDIN:
        lines.append(config.SENDER_LINKEDIN)
    return "\n".join(lines)


def _build_html_body(plain_text: str) -> str:
    """Wrap plain text into a simple, clean HTML email."""
    # Convert newlines to <br> for HTML
    html_content = plain_text.replace("\n", "<br>\n")
    return dedent(f"""\
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="UTF-8">
          <style>
            body {{ font-family: Arial, sans-serif; font-size: 15px;
                    line-height: 1.6; color: #222; max-width: 600px; margin: auto; }}
            .signoff {{ margin-top: 24px; color: #444; }}
          </style>
        </head>
        <body>
          {html_content}
        </body>
        </html>
    """)


# ── Message builder ───────────────────────────────────────────────────────────

def build_message(
    *,
    to: str,
    intro_name: str,
    subject: str,
    ai_body: str,
    cv_path: Path,
) -> MIMEMultipart:
    """
    Construct a MIMEMultipart email message.

    Args:
        to:           Recruiter's email address.
        intro_name:   First name for the greeting (e.g. "Sarah").
        subject:      Email subject line.
        ai_body:      AI-generated email body (plain text, no greeting/signoff).
        cv_path:      Path to the PDF CV to attach.

    Returns:
        A fully built MIMEMultipart message (ready to send).

    Raises:
        FileNotFoundError if cv_path does not exist.
    """
    greeting = f"Dear {intro_name}," if intro_name else "Dear Hiring Manager,"
    signoff = _build_signoff()
    full_plain = f"{greeting}\n\n{ai_body}\n{signoff}"
    full_html = _build_html_body(full_plain)

    msg = MIMEMultipart("mixed")
    msg["From"] = f"{config.SENDER_NAME} <{config.SENDER_EMAIL}>"
    msg["To"] = to
    msg["Subject"] = subject

    # Body — prefer HTML, fallback to plain text
    body_alt = MIMEMultipart("alternative")
    body_alt.attach(MIMEText(full_plain, "plain", "utf-8"))
    body_alt.attach(MIMEText(full_html, "html", "utf-8"))
    msg.attach(body_alt)

    # CV Attachment
    if not cv_path.exists():
        raise FileNotFoundError(
            f"[email_sender] CV not found at: {cv_path}\n"
            "  → Place your resume at the configured CV_PATH location."
        )

    ctype, _ = mimetypes.guess_type(str(cv_path))
    maintype, subtype = (ctype or "application/octet-stream").split("/", 1)

    with open(cv_path, "rb") as f:
        attachment = MIMEBase(maintype, subtype)
        attachment.set_payload(f.read())

    encoders.encode_base64(attachment)
    attachment.add_header(
        "Content-Disposition",
        "attachment",
        filename=cv_path.name,
    )
    msg.attach(attachment)

    return msg


# ── Delivery ──────────────────────────────────────────────────────────────────

def send_email(msg: MIMEMultipart) -> None:
    """
    Send a pre-built MIMEMultipart message via SMTP.

    If config.DRY_RUN is True, logs a preview and returns without connecting.

    Raises:
        smtplib.SMTPException on delivery failure.
    """
    to_addr = msg["To"]
    subject = msg["Subject"]

    if config.DRY_RUN:
        logger.info(
            "[DRY RUN] Would send to <%s> | Subject: '%s'", to_addr, subject
        )
        return

    logger.debug("Connecting to SMTP %s:%d", config.SMTP_HOST, config.SMTP_PORT)
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.send_message(msg)

    logger.info("✅ Email sent to <%s> | '%s'", to_addr, subject)


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from rich.console import Console

    c = Console()
    c.rule("[bold cyan]Email Builder Self-Test")

    # Build a dummy message (CV path doesn't need to exist for header inspection)
    dummy_cv = config.CV_PATH

    # Create a placeholder CV for the test if it doesn't exist
    if not dummy_cv.exists():
        dummy_cv.write_bytes(b"%PDF-1.4 placeholder")
        c.print("[yellow]⚠ Created placeholder cv.pdf for test. Replace with your real CV.[/]")

    msg = build_message(
        to="test@example.com",
        intro_name="Alex",
        subject="Application for Senior Engineer at Test Corp",
        ai_body=(
            "I was excited to see your opening for a Senior Engineer. "
            "My five years building scalable Python APIs align well with your stack. "
            "I would love to discuss how I can contribute to your team."
        ),
        cv_path=dummy_cv,
    )

    c.rule("Message Headers")
    for key in ("From", "To", "Subject"):
        c.print(f"[bold]{key}:[/] {msg[key]}")

    c.rule("Parts")
    for i, part in enumerate(msg.walk()):
        c.print(f"  Part {i}: {part.get_content_type()}")

    c.rule("Done — no email was sent")
