"""
job_applier.py — Main orchestrator for the Job Application Automation System.

Usage:
    python job_applier.py                # run all rows (DRY_RUN respects .env)
    python job_applier.py --dry-run      # force dry run regardless of .env
    python job_applier.py --limit 3      # process first 3 rows only
    python job_applier.py --company Acme # filter to rows matching company name
    python job_applier.py --help         # show usage
"""
from __future__ import annotations

import argparse
import random
import time
import sys
from pathlib import Path

from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

import config
from ai_generator import AIGenerationError, generate_email_body
from email_sender import build_message, send_email
from utils import (
    append_log,
    console,
    estimate_cost,
    make_log_row,
    read_jobs,
    setup_logging,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI-powered job application email automator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Compose and log emails but do NOT send them (overrides .env DRY_RUN).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Only process the first N rows in jobs.csv.",
    )
    parser.add_argument(
        "--company",
        type=str,
        default=None,
        metavar="NAME",
        help="Filter to rows whose company_name contains this string (case-insensitive).",
    )
    return parser.parse_args()


def process_job(row: dict, dry_run: bool, logger) -> dict:
    """
    Process a single job row end-to-end.
    Returns a log-row dict with status and metrics.
    """
    company = row["company_name"]
    position = row["position"]
    to_email = row["recruiter_email"]
    intro_name = row["intro_name"]
    job_description = row["job_description"]
    custom_note = row.get("custom_note", "")

    # Resolve CV path: per-row override or global default
    cv_path_str = row.get("cv_path", "").strip()
    cv_path = (
        config.BASE_DIR / cv_path_str if cv_path_str else config.CV_PATH
    )

    # ── Step 1: Generate AI email body ───────────────────────────────────────
    logger.info("🤖 Generating email for [%s @ %s]", position, company)
    try:
        ai_body, tokens = generate_email_body(
            company=company,
            position=position,
            job_description=job_description,
            custom_note=custom_note,
        )
    except AIGenerationError as exc:
        logger.error("AI generation failed: %s", exc)
        return make_log_row(
            company=company, position=position, email=to_email,
            status="failed_ai", error=str(exc),
        )

    cost = estimate_cost(tokens, config.GEMINI_MODEL if config.AI_PROVIDER == "gemini" else config.GROK_MODEL)

    # ── Step 2: Build subject ─────────────────────────────────────────────────
    subject = config.EMAIL_SUBJECT_TEMPLATE.format(position=position, company=company)

    # ── Step 3: Build MIME message ────────────────────────────────────────────
    try:
        msg = build_message(
            to=to_email,
            intro_name=intro_name,
            subject=subject,
            ai_body=ai_body,
            cv_path=cv_path,
        )
    except FileNotFoundError as exc:
        logger.error("CV file missing: %s", exc)
        return make_log_row(
            company=company, position=position, email=to_email,
            status="failed_cv", error=str(exc), tokens=tokens, cost=cost,
        )

    # ── Step 4: Send (with retry logic) ──────────────────────────────────────
    effective_dry_run = dry_run or config.DRY_RUN
    attempt = 0
    last_error = ""

    while attempt <= config.MAX_RETRIES:
        try:
            send_email(msg)  # respects DRY_RUN inside
            status = "dry_run" if effective_dry_run else "success"
            break
        except Exception as exc:
            attempt += 1
            last_error = str(exc)
            if attempt <= config.MAX_RETRIES:
                wait = 2 ** attempt  # exponential backoff: 2s, 4s
                logger.warning("SMTP error (attempt %d/%d): %s. Retrying in %ds…",
                               attempt, config.MAX_RETRIES, exc, wait)
                time.sleep(wait)
            else:
                logger.error("Email delivery failed after %d attempts: %s", config.MAX_RETRIES + 1, exc)
                status = "failed_smtp"

    # ── Step 5: Print preview to console ─────────────────────────────────────
    if effective_dry_run:
        console.print(Panel(
            f"[bold]To:[/] {to_email}\n"
            f"[bold]Subject:[/] {subject}\n\n"
            f"Dear {intro_name},\n\n{ai_body}",
            title=f"[cyan]Email Preview — {company}[/]",
            expand=False,
        ))

    return make_log_row(
        company=company, position=position, email=to_email,
        status=status, tokens=tokens, cost=cost, error=last_error,
    )


def print_summary(results: list[dict]) -> None:
    """Print a rich summary table after all rows are processed."""
    table = Table(title="📊 Run Summary", show_lines=True)
    table.add_column("Company", style="cyan")
    table.add_column("Position", style="white")
    table.add_column("Status", style="bold")
    table.add_column("Tokens", justify="right")
    table.add_column("Cost USD", justify="right")

    status_colors = {
        "success":    "green",
        "dry_run":    "yellow",
        "failed_ai":  "red",
        "failed_smtp":"red",
        "failed_cv":  "red",
    }

    for r in results:
        color = status_colors.get(r["status"], "white")
        table.add_row(
            r["company_name"],
            r["position"],
            f"[{color}]{r['status']}[/]",
            str(r["tokens_used"]),
            r["cost_usd_estimate"],
        )

    console.print(table)


def main() -> None:
    args = parse_args()

    # Override DRY_RUN if CLI flag is set
    if args.dry_run:
        import config as _cfg
        _cfg.DRY_RUN = True  # type: ignore[attr-defined]

    # Setup logging and directories
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = setup_logging(config.LOG_DIR)

    # Banner
    mode_label = "[bold yellow]DRY RUN[/]" if (args.dry_run or config.DRY_RUN) else "[bold green]LIVE SEND[/]"
    console.rule(f"[bold blue]Job Application Automator[/] — {mode_label}")
    console.print(f"  AI Provider : [cyan]{config.AI_PROVIDER.upper()}[/]  |  "
                  f"SMTP : {config.SMTP_HOST}:{config.SMTP_PORT}  |  "
                  f"Jobs CSV : {config.JOBS_CSV_PATH}")
    console.print()

    # Load jobs
    try:
        jobs_df = read_jobs(config.JOBS_CSV_PATH)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[bold red]Error loading jobs.csv:[/] {exc}")
        sys.exit(1)

    # Apply filters
    if args.company:
        jobs_df = jobs_df[jobs_df["company_name"].str.contains(args.company, case=False)]
        console.print(f"  [dim]Filtered to company='{args.company}': {len(jobs_df)} row(s)[/]")

    if args.limit:
        jobs_df = jobs_df.head(args.limit)
        console.print(f"  [dim]Limited to first {args.limit} row(s)[/]")

    total = len(jobs_df)
    if total == 0:
        console.print("[yellow]No jobs to process. Check your filters or jobs.csv.[/]")
        sys.exit(0)

    console.print(f"\n  Processing [bold]{total}[/] job(s)…\n")

    results: list[dict] = []

    for idx, (_, row) in enumerate(jobs_df.iterrows(), start=1):
        console.rule(f"[dim]Job {idx}/{total}[/]")
        row_dict = row.to_dict()

        log_entry = process_job(row_dict, dry_run=args.dry_run, logger=logger)
        results.append(log_entry)
        append_log(config.SENT_LOG_PATH, log_entry)

        # Rate-limit delay (skip after the last item)
        if idx < total:
            delay = random.uniform(config.MIN_DELAY_SECONDS, config.MAX_DELAY_SECONDS)
            console.print(f"\n  [dim]⏱  Waiting {delay:.0f}s before next send…[/]\n")
            time.sleep(delay)

    # Final summary
    console.print()
    print_summary(results)
    console.print(f"\n  Log written → [cyan]{config.SENT_LOG_PATH}[/]")
    console.rule("[bold blue]Done[/]")


if __name__ == "__main__":
    main()
