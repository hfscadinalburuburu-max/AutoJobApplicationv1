"""
runbot.py — Telegram Bot as a Django Management Command.
"""
from __future__ import annotations

import asyncio
import logging
import re
from asgiref.sync import sync_to_async

from django.core.management.base import BaseCommand
from django.utils import timezone

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode

import config
from core.models import JobApplication
from services.ai_generator import generate_email_body, extract_job_details, AIGenerationError
from services.job_discovery import search_jobs, fetch_job_description
from services.email_sender import build_message, send_email

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

STATUS_EMOJI = {
    "pending":     "⏳",
    "applied":     "📤",
    "interview":   "🎯",
    "rejected":    "❌",
    "no_response": "🔇",
    "offer":       "🎉",
}
STATUSES = [s[0] for s in JobApplication.STATUS_CHOICES]

# ── Conversation states ───────────────────────────────────────────────────────
ADD_COMPANY, ADD_POSITION, ADD_EMAIL, ADD_JD, ADD_CONFIRM = range(5)
APPLY_CONFIRM = 10

# ── Auth guard ────────────────────────────────────────────────────────────────
def _is_allowed(update: Update) -> bool:
    if not config.TELEGRAM_ALLOWED_CHAT_IDS:
        return True
    return str(update.effective_chat.id) in config.TELEGRAM_ALLOWED_CHAT_IDS

async def _deny(update: Update) -> None:
    await update.message.reply_text(
        "⛔ You are not authorized to use this bot.\n"
        f"Your chat ID: `{update.effective_chat.id}`\n"
        "Add it to `TELEGRAM_ALLOWED_CHAT_IDS` in your `.env`.",
        parse_mode=ParseMode.MARKDOWN,
    )

def _fmt_app(app: JobApplication) -> str:
    emoji = STATUS_EMOJI.get(app.status, "•")
    lines = [
        f"{emoji} *{app.company}* — {app.position}",
        f"   Status: `{app.status}`",
    ]
    if app.date_applied:
        lines.append(f"   Applied: {app.date_applied.strftime('%Y-%m-%d')}")
    if app.recruiter_email:
        lines.append(f"   Email: {app.recruiter_email}")
    if app.notes:
        lines.append(f"   Notes: _{app.notes[:80]}_")
    lines.append(f"   ID: `#{app.id}`")
    return "\n".join(lines)


# ── Commands ────────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return await _deny(update)
    text = (
        "👋 *Job Application Bot* is ready!\n\n"
        "Send me a *job URL* and I'll process it automatically, or use these commands:\n\n"
        "📋 `/list` — View recent applications\n"
        "🔍 `/search <keywords>` — Find new jobs\n"
        "🚀 `/apply <url>` — Process a job link\n"
        "➕ `/add` — Add a job manually\n"
        "📊 `/stats` — Application statistics\n"
        "🔄 `/update <id> <status>` — Update status\n"
        "❓ `/help` — Full command reference\n"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return await _deny(update)
    text = (
        "📖 *Available Commands*\n\n"
        "`/start` — Welcome & quick guide\n"
        "`/list [n]` — Last N applications (default 10)\n"
        "`/status <company>` — Search by company name\n"
        "`/apply <url>` — Process a job posting URL\n"
        "`/add` — Guided flow to add a job manually\n"
        "`/search <keywords>` — Discover new matching jobs\n"
        "`/update <id> <status>` — Change application status\n"
        f"  Statuses: `{'` `'.join(STATUSES)}`\n"
        "`/stats` — Dashboard statistics\n"
        "`/help` — This message\n\n"
        "💡 *Tip*: Just paste a job URL (no command) to auto-process it!"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return await _deny(update)
    
    @sync_to_async
    def get_stats():
        stats = {'total': JobApplication.objects.count()}
        for status in STATUSES:
            stats[status] = JobApplication.objects.filter(status=status).count()
        return stats
        
    stats = await get_stats()
    lines = ["📊 *Application Statistics*\n"]
    for status in STATUSES:
        emoji = STATUS_EMOJI.get(status, "•")
        count = stats.get(status, 0)
        bar = "█" * count + "░" * max(0, 10 - count)
        lines.append(f"{emoji} `{status:<12}` {bar} {count}")
    lines.append(f"\n*Total:* {stats.get('total', 0)} applications")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return await _deny(update)
    n = 10
    if context.args:
        try:
            n = min(int(context.args[0]), 25)
        except ValueError: pass

    @sync_to_async
    def get_apps():
        return list(JobApplication.objects.all()[:n])
        
    apps = await get_apps()
    if not apps:
        await update.message.reply_text("No applications tracked yet. Use `/add` or `/apply` to get started.")
        return

    chunks = []
    current = f"📋 *Last {min(n, len(apps))} Applications*\n\n"
    for app in apps:
        entry = _fmt_app(app) + "\n\n"
        if len(current) + len(entry) > 3800:
            chunks.append(current)
            current = entry
        else:
            current += entry
    chunks.append(current)

    for chunk in chunks:
        await update.message.reply_text(chunk.strip(), parse_mode=ParseMode.MARKDOWN)

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return await _deny(update)
    if not context.args:
        await update.message.reply_text("Usage: `/status <company name>`", parse_mode=ParseMode.MARKDOWN)
        return

    query = " ".join(context.args)
    @sync_to_async
    def search_apps():
        return list(JobApplication.objects.filter(company__icontains=query) | JobApplication.objects.filter(position__icontains=query))
    
    results = await search_apps()
    if not results:
        await update.message.reply_text(f"No applications found matching *{query}*.", parse_mode=ParseMode.MARKDOWN)
        return

    text = f"🔍 Results for *{query}*:\n\n" + "\n\n".join(_fmt_app(a) for a in results[:5])
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def cmd_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return await _deny(update)
    if len(context.args) < 2:
        await update.message.reply_text(f"Usage: `/update <id> <status>`\nStatuses: {' | '.join(STATUSES)}", parse_mode=ParseMode.MARKDOWN)
        return

    try:
        app_id = int(context.args[0].lstrip("#"))
    except ValueError:
        return await update.message.reply_text("❌ ID must be a number", parse_mode=ParseMode.MARKDOWN)

    new_status = context.args[1].lower()
    if new_status not in STATUSES:
        return await update.message.reply_text(f"❌ Unknown status `{new_status}`. Choose: {', '.join(STATUSES)}", parse_mode=ParseMode.MARKDOWN)

    @sync_to_async
    def update_app():
        try:
            app = JobApplication.objects.get(pk=app_id)
            notes = " ".join(context.args[2:]) if len(context.args) > 2 else app.notes
            app.status = new_status
            app.notes = notes
            app.save()
            return app
        except JobApplication.DoesNotExist:
            return None
            
    app = await update_app()
    if not app:
        return await update.message.reply_text(f"❌ No application found with ID #{app_id}")

    emoji = STATUS_EMOJI.get(new_status, "•")
    await update.message.reply_text(f"{emoji} Updated *{app.company}* → `{new_status}`", parse_mode=ParseMode.MARKDOWN)

async def cmd_apply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return await _deny(update)
    if not context.args:
        return await update.message.reply_text("Usage: `/apply <job_url>`", parse_mode=ParseMode.MARKDOWN)
    await _process_job_url(update, context, context.args[0])

async def _process_job_url(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str) -> None:
    msg = await update.message.reply_text("⏳ Fetching job description from URL…")

    match = re.search(r"https?://\S+", url)
    if not match:
        return await msg.edit_text("❌ Invalid URL provided.")
    url = match.group(0)

    try:
        jd_text = await asyncio.to_thread(fetch_job_description, url)
    except Exception as e:
        return await msg.edit_text(f"❌ Error fetching URL: {e}")

    if not jd_text:
        return await msg.edit_text("❌ Could not fetch the job description from that URL.")

    await msg.edit_text("🤖 Extracting job details with AI…")
    try:
        details = await asyncio.to_thread(extract_job_details, jd_text)
    except AIGenerationError as e:
        return await msg.edit_text(f"❌ AI extraction failed: {e}")

    company = str(details.get("company_name", "Unknown Company"))[:255]
    position = str(details.get("position", "Unknown Position"))[:255]
    recruiter_email = str(details.get("recruiter_email", ""))[:254]
    intro_name = str(details.get("intro_name", "Hiring Manager"))[:100]
    job_description = str(details.get("job_description", jd_text[:1000]))[:10000]

    await msg.edit_text(
        f"✅ *Job Extracted:*\n🏢 {company}\n💼 {position}\n📧 {recruiter_email}\n🤖 Generating email…",
        parse_mode=ParseMode.MARKDOWN,
    )

    try:
        email_body, _ = await asyncio.to_thread(generate_email_body, company, position, job_description)
    except AIGenerationError as e:
        return await msg.edit_text(f"❌ Email generation failed: {e}")

    @sync_to_async
    def create_app():
        return JobApplication.objects.create(
            company=company, position=position, recruiter_email=recruiter_email,
            intro_name=intro_name, job_link=url, job_description=job_description,
            generated_email=email_body, source="telegram"
        )
    app = await create_app()

    context.user_data["pending_apply"] = {
        "app_id": app.id, "company": company, "position": position,
        "to_email": recruiter_email, "intro_name": intro_name, "email_body": email_body,
    }

    preview_text = (
        f"📧 *Email Preview — {company}*\n\n*To:* {recruiter_email or '(no email found)'}\n"
        f"Dear {intro_name},\n\n{email_body[:600]}…"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✉️ Send Email", callback_data=f"send_{app.id}"), InlineKeyboardButton("💾 Save Only", callback_data=f"save_{app.id}")],
        [InlineKeyboardButton("❌ Discard", callback_data=f"discard_{app.id}")]
    ])
    await msg.edit_text(preview_text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    action, app_id_str = query.data.split("_", 1)
    app_id = int(app_id_str)

    @sync_to_async
    def get_app():
        try: return JobApplication.objects.get(pk=app_id)
        except JobApplication.DoesNotExist: return None
    app = await get_app()
    if not app:
        return await query.edit_message_text("❌ Application not found.")

    if action == "send":
        if not app.recruiter_email:
            return await query.edit_message_text("⚠️ No email found. Update via `/update {id} applied` later.")
        try:
            subject = config.EMAIL_SUBJECT_TEMPLATE.format(position=app.position, company=app.company)
            msg = build_message(app.recruiter_email, app.intro_name or "Hiring Manager", subject, app.generated_email, config.CV_PATH)
            await asyncio.to_thread(send_email, msg)
            
            @sync_to_async
            def save_sent():
                app.status = "applied"
                app.date_applied = timezone.now()
                app.save()
            await save_sent()
            
            await query.edit_message_text(f"✅ Email sent to *{app.recruiter_email}*!\nSaved as `applied`.", parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            await query.edit_message_text(f"❌ Send failed: {e}")

    elif action == "save":
        await query.edit_message_text(f"💾 Saved as *pending* — *{app.company}*\nID: `#{app_id}`", parse_mode=ParseMode.MARKDOWN)

    elif action == "discard":
        @sync_to_async
        def delete_app(): app.delete()
        await delete_app()
        await query.edit_message_text(f"🗑️ Discarded *{app.company}*", parse_mode=ParseMode.MARKDOWN)


# ── /add conversation ──

async def cmd_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _is_allowed(update):
        await _deny(update)
        return ConversationHandler.END
    context.user_data.clear()
    await update.message.reply_text("➕ *Add Job Manually* — Step 1/4\n\nEnter the *company name*:", parse_mode=ParseMode.MARKDOWN)
    return ADD_COMPANY

async def add_company(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["company"] = update.message.text.strip()[:255]
    await update.message.reply_text("Step 2/4 — Enter the *position*:", parse_mode=ParseMode.MARKDOWN)
    return ADD_POSITION

async def add_position(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["position"] = update.message.text.strip()[:255]
    await update.message.reply_text("Step 3/4 — Enter the *recruiter email* (or `skip`):", parse_mode=ParseMode.MARKDOWN)
    return ADD_EMAIL

async def add_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email_text = update.message.text.strip().lower()
    context.user_data["email"] = "" if email_text == "skip" else email_text[:254]
    await update.message.reply_text("Step 4/4 — Paste the *JD* (or `skip`):", parse_mode=ParseMode.MARKDOWN)
    return ADD_JD

async def add_jd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    jd_text = update.message.text.strip()
    context.user_data["jd"] = "" if jd_text.lower() == "skip" else jd_text[:10000]
    d = context.user_data
    await update.message.reply_text(
        f"✅ *Review:*\n🏢 {d['company']}\n💼 {d['position']}\n📧 {d.get('email')}\n\nReply *yes* to save, or *no* to cancel.",
        parse_mode=ParseMode.MARKDOWN
    )
    return ADD_CONFIRM

async def add_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text.strip().lower() in ("yes", "y", "save"):
        d = context.user_data
        @sync_to_async
        def save_manual():
            return JobApplication.objects.create(
                company=d["company"], position=d["position"],
                recruiter_email=d.get("email", ""), job_description=d.get("jd", ""),
                source="telegram_manual"
            )
        app = await save_manual()
        await update.message.reply_text(f"✅ Saved! ID `#{app.id}`", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END

async def add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ── URL handler ──

async def handle_url_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return await _deny(update)
    match = re.search(r"https?://\S+", update.message.text or "")
    if match:
        await _process_job_url(update, context, match.group(0))


# ── Search ──
async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return await _deny(update)
    kw = " ".join(context.args) if context.args else config.JOB_KEYWORDS
    msg = await update.message.reply_text(f"🔍 Searching for *{kw}* jobs…", parse_mode=ParseMode.MARKDOWN)
    try:
        jobs = await asyncio.to_thread(search_jobs, keywords=kw, limit_per_source=5)
    except Exception as e:
        return await msg.edit_text(f"❌ Search failed: {e}")

    if not jobs:
        return await msg.edit_text("No new jobs found.")

    lines = [f"🆕 *Found {len(jobs)} new job(s)*:\n"]
    for i, j in enumerate(jobs[:8], 1):
        lines.append(f"*{i}. {j.position}* @ {j.company}\n   [{j.source}] {j.link}\n")
    await msg.edit_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)


class Command(BaseCommand):
    help = "Run the Telegram Bot"

    def handle(self, *args, **options):
        if not config.TELEGRAM_BOT_TOKEN:
            self.stdout.write(self.style.ERROR("TELEGRAM_BOT_TOKEN is not set."))
            return

        app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

        add_conv = ConversationHandler(
            entry_points=[CommandHandler("add", cmd_add_start)],
            states={
                ADD_COMPANY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_company)],
                ADD_POSITION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_position)],
                ADD_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_email)],
                ADD_JD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_jd)],
                ADD_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_confirm)],
            },
            fallbacks=[CommandHandler("cancel", add_cancel)],
        )

        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("help", cmd_help))
        app.add_handler(CommandHandler("stats", cmd_stats))
        app.add_handler(CommandHandler("list", cmd_list))
        app.add_handler(CommandHandler("status", cmd_status))
        app.add_handler(CommandHandler("update", cmd_update))
        app.add_handler(CommandHandler("apply", cmd_apply))
        app.add_handler(CommandHandler("search", cmd_search))
        app.add_handler(add_conv)
        app.add_handler(CallbackQueryHandler(callback_handler))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url_message))

        self.stdout.write(self.style.SUCCESS("🤖 Bot starting — polling for updates…"))
        app.run_polling(allowed_updates=Update.ALL_TYPES)
