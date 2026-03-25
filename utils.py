"""
utils.py — Shared helpers: logging setup, CSV I/O, cost estimation, console.
"""
from __future__ import annotations

import csv
import logging
import logging.handlers
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from rich.console import Console
from rich.logging import RichHandler

# ── Shared rich console ───────────────────────────────────────────────────────
console = Console()

# Required columns in jobs.csv
REQUIRED_COLUMNS = {"company_name", "position", "recruiter_email", "intro_name", "job_description"}

# Columns written to sent_log.csv
LOG_COLUMNS = [
    "timestamp",
    "company_name",
    "position",
    "recruiter_email",
    "status",
    "tokens_used",
    "cost_usd_estimate",
    "error",
]

# ── Logging setup ─────────────────────────────────────────────────────────────

def setup_logging(log_dir: Path, level: int = logging.INFO) -> logging.Logger:
    """Configure root logger with rotating file + rich stderr handlers."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "job_applier.log"

    logger = logging.getLogger("job_applier")
    logger.setLevel(level)

    # Avoid adding duplicate handlers on repeated calls
    if logger.handlers:
        return logger

    # Rotating file handler (5 MB × 3 backups)
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s")
    )
    file_handler.setLevel(level)

    # Rich console handler (colorful, human-readable)
    rich_handler = RichHandler(console=console, rich_tracebacks=True, show_path=False)
    rich_handler.setLevel(level)

    logger.addHandler(file_handler)
    logger.addHandler(rich_handler)
    return logger


# ── CSV helpers ───────────────────────────────────────────────────────────────

def read_jobs(path: Path) -> pd.DataFrame:
    """
    Read jobs.csv and return as a DataFrame.
    Raises FileNotFoundError or ValueError on problems.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"[utils] Jobs file not found: {path}\n"
            "  → Create jobs.csv (copy the sample) and add your target roles."
        )

    df = pd.read_csv(path, dtype=str).fillna("")
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"[utils] jobs.csv is missing required columns: {', '.join(sorted(missing))}\n"
            "  → Required: company_name, position, recruiter_email, intro_name, job_description"
        )

    # Strip whitespace from all string cells
    df = df.apply(lambda col: col.str.strip() if col.dtype == object else col)
    return df


def append_log(log_path: Path, row: dict[str, Any]) -> None:
    """Append one result row to sent_log.csv, creating it with headers if new."""
    file_exists = log_path.exists()
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerow({col: row.get(col, "") for col in LOG_COLUMNS})


def make_log_row(
    *,
    company: str,
    position: str,
    email: str,
    status: str,
    tokens: int = 0,
    cost: float = 0.0,
    error: str = "",
) -> dict[str, Any]:
    """Build a standardised log row dict."""
    return {
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "company_name": company,
        "position": position,
        "recruiter_email": email,
        "status": status,
        "tokens_used": tokens,
        "cost_usd_estimate": f"{cost:.6f}",
        "error": error,
    }


# ── Token cost estimation ─────────────────────────────────────────────────────

# Very rough per-1K-token pricing (input + output blended). Update as needed.
_COST_PER_1K: dict[str, float] = {
    "gemini-2.0-flash": 0.000075,   # $0.075 / 1M tokens
    "gemini-1.5-pro":   0.00175,
    "grok-3":           0.003,
    "gpt-4o":           0.005,
}


def estimate_cost(tokens: int, model: str) -> float:
    """Return estimated USD cost for the given token count and model."""
    rate = _COST_PER_1K.get(model, 0.001)
    return (tokens / 1000) * rate
