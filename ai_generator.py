"""
ai_generator.py — AI email body generation via Gemini or Grok.

Supports:
  - Google Gemini (google-generativeai SDK)
  - xAI Grok / OpenAI-compatible (openai SDK)

Toggle with AI_PROVIDER env var ("gemini" | "grok").
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import config

logger = logging.getLogger("job_applier")

# ── Custom exception ──────────────────────────────────────────────────────────


class AIGenerationError(Exception):
    """Raised when the AI API fails to generate an email body."""


# ── Prompt builders ───────────────────────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = """\
You are a professional job application assistant. Your task is to write the BODY of a
cold-outreach application email on behalf of the candidate described below.

--- CANDIDATE PROFILE ---
{profile}
--- END PROFILE ---

Rules:
1. Write ONLY the email body — no subject line, no "Dear", no sign-off.
2. Length: 120–200 words. Be concise and punchy.
3. Tone: professional yet warm and genuine. Avoid buzzwords and clichés.
4. Highlight exactly 2–3 specific ways the candidate's background matches the role.
5. End with a clear, polite call-to-action (e.g. request for a call).
6. Do NOT invent facts — only use what's in the candidate profile and job description.
7. Output plain text only. No markdown, no bullet points, no asterisks.
"""

USER_PROMPT_TEMPLATE = """\
Company: {company}
Position: {position}
{custom_note_section}
--- JOB DESCRIPTION ---
{job_description}
--- END JOB DESCRIPTION ---

Write the email body now.
"""


def _build_prompts(
    company: str,
    position: str,
    job_description: str,
    custom_note: str = "",
) -> tuple[str, str]:
    system = SYSTEM_PROMPT_TEMPLATE.format(profile=config.PROFILE_SUMMARY)
    custom_note_section = (
        f"Custom note to include naturally: {custom_note}\n" if custom_note else ""
    )
    user = USER_PROMPT_TEMPLATE.format(
        company=company,
        position=position,
        job_description=job_description,
        custom_note_section=custom_note_section,
    )
    return system, user


# ── Gemini implementation ─────────────────────────────────────────────────────


def _generate_gemini(system: str, user: str) -> tuple[str, int]:
    """Call Google Gemini API. Returns (body_text, total_tokens)."""
    try:
        import google.generativeai as genai  # type: ignore
    except ImportError:
        raise AIGenerationError(
            "google-generativeai package not installed. Run: pip install google-generativeai"
        )

    genai.configure(api_key=config.GEMINI_API_KEY)
    model = genai.GenerativeModel(
        model_name=config.GEMINI_MODEL,
        system_instruction=system,
    )

    response = model.generate_content(user)

    body = response.text.strip()
    # Token counting: Gemini returns usage_metadata
    try:
        tokens = (
            response.usage_metadata.prompt_token_count
            + response.usage_metadata.candidates_token_count
        )
    except AttributeError:
        tokens = 0

    return body, tokens


# ── Grok (OpenAI-compatible) implementation ───────────────────────────────────


def _generate_grok(system: str, user: str) -> tuple[str, int]:
    """Call xAI Grok via OpenAI-compatible API. Returns (body_text, total_tokens)."""
    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        raise AIGenerationError(
            "openai package not installed. Run: pip install openai"
        )

    client = OpenAI(api_key=config.GROK_API_KEY, base_url=config.GROK_BASE_URL)
    response = client.chat.completions.create(
        model=config.GROK_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.7,
        max_tokens=400,
    )

    body = response.choices[0].message.content.strip()
    tokens = response.usage.total_tokens if response.usage else 0
    return body, tokens


# ── Public API ────────────────────────────────────────────────────────────────


def generate_email_body(
    company: str,
    position: str,
    job_description: str,
    custom_note: str = "",
) -> tuple[str, int]:
    """
    Generate a personalised email body for the given job.

    Returns:
        (email_body: str, tokens_used: int)

    Raises:
        AIGenerationError on any API failure.
    """
    system, user = _build_prompts(company, position, job_description, custom_note)
    logger.debug("Generating email for %s @ %s using provider=%s", position, company, config.AI_PROVIDER)

    try:
        if config.AI_PROVIDER == "gemini":
            body, tokens = _generate_gemini(system, user)
        elif config.AI_PROVIDER == "grok":
            body, tokens = _generate_grok(system, user)
        else:
            raise AIGenerationError(
                f"Unknown AI_PROVIDER: '{config.AI_PROVIDER}'. Use 'gemini' or 'grok'."
            )
    except AIGenerationError:
        raise
    except Exception as exc:
        raise AIGenerationError(
            f"AI API call failed for {position} @ {company}: {exc}"
        ) from exc

    logger.debug("Generated %d chars, ~%d tokens", len(body), tokens)
    return body, tokens


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from rich.console import Console

    c = Console()
    c.rule("[bold cyan]AI Generator Self-Test")
    c.print(f"Provider : [yellow]{config.AI_PROVIDER}[/]")
    c.print(f"Model    : [yellow]{config.GEMINI_MODEL if config.AI_PROVIDER == 'gemini' else config.GROK_MODEL}[/]\n")

    sample_jd = (
        "We are looking for a Senior Python Engineer to build scalable APIs. "
        "Requirements: Python, FastAPI, PostgreSQL, Docker. 4+ years experience."
    )

    body, tokens = generate_email_body(
        company="Test Corp",
        position="Senior Python Engineer",
        job_description=sample_jd,
        custom_note="I love your open-source work on GitHub.",
    )

    c.rule("Generated Email Body")
    c.print(body)
    c.rule()
    c.print(f"Tokens used: [bold]{tokens}[/]")
