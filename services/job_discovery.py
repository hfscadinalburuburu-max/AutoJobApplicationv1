"""
job_discovery.py — Auto-search for jobs from multiple sources.

Sources:
  - Indeed (scraping)
  - Google Jobs (via SerpAPI or scraping)
  - LinkedIn (public listings)

Usage:
    python job_discovery.py --keywords "Python developer" --location "Kenya" --sources indeed google
"""
from __future__ import annotations

import argparse
import logging
import random
import time
import re
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup

import config

logger = logging.getLogger("job_applier")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class JobResult:
    company: str
    position: str
    location: str
    link: str
    snippet: str
    source: str
    salary: str = ""
    posted: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "company": self.company,
            "position": self.position,
            "location": self.location,
            "link": self.link,
            "snippet": self.snippet,
            "source": self.source,
            "salary": self.salary,
            "posted": self.posted,
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sleep(min_s: float = 1.5, max_s: float = 3.5) -> None:
    time.sleep(random.uniform(min_s, max_s))


def _get(url: str, params: dict | None = None, timeout: int = 15) -> requests.Response | None:
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp
    except requests.RequestException as e:
        logger.warning("HTTP error fetching %s: %s", url, e)
        return None


# ── Indeed scraper ────────────────────────────────────────────────────────────

def search_indeed(
    keywords: str,
    location: str,
    remote: bool = False,
    limit: int = 20,
) -> list[JobResult]:
    """Scrape Indeed public job listings (no login required)."""
    results = []
    query = keywords
    if remote:
        query += " remote"

    url = "https://www.indeed.com/jobs"
    params = {
        "q": query,
        "l": location,
        "sort": "date",
        "limit": min(limit, 50),
    }

    resp = _get(url, params=params)
    if not resp:
        logger.warning("Indeed: no response")
        return results

    soup = BeautifulSoup(resp.text, "lxml")

    # Indeed job cards — multiple possible selectors (they change frequently)
    cards = (
        soup.select("div.job_seen_beacon")
        or soup.select("div[data-jk]")
        or soup.select("div.jobsearch-SerpJobCard")
    )

    for card in cards[:limit]:
        try:
            title_el = card.select_one("h2.jobTitle span[title], h2.jobTitle a span, h2 a")
            company_el = card.select_one("span.companyName, [data-testid='company-name']")
            location_el = card.select_one("div.companyLocation, [data-testid='text-location']")
            snippet_el = card.select_one("div.job-snippet, div[data-testid='jobDescSnippet']")
            salary_el = card.select_one("div.salary-snippet, div[data-testid='attribute_snippet_testid']")

            title = title_el.get_text(strip=True) if title_el else "Unknown"
            company = company_el.get_text(strip=True) if company_el else "Unknown"
            loc = location_el.get_text(strip=True) if location_el else location
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            salary = salary_el.get_text(strip=True) if salary_el else ""

            # Build job link
            jk = card.get("data-jk") or ""
            if not jk:
                link_el = card.select_one("a[id^='job_']")
                jk = link_el["id"].replace("job_", "") if link_el else ""
            link = f"https://www.indeed.com/viewjob?jk={jk}" if jk else ""

            if title and company:
                results.append(JobResult(
                    company=company,
                    position=title,
                    location=loc,
                    link=link,
                    snippet=snippet,
                    source="Indeed",
                    salary=salary,
                ))
        except Exception as e:
            logger.debug("Indeed card parse error: %s", e)

    logger.info("Indeed: found %d results for '%s' in '%s'", len(results), keywords, location)
    return results


# ── Google Jobs via SerpAPI ───────────────────────────────────────────────────

def search_google_serpapi(
    keywords: str,
    location: str,
    remote: bool = False,
    limit: int = 20,
) -> list[JobResult]:
    """Use SerpAPI to query Google Jobs (requires SERPAPI_KEY)."""
    if not config.SERPAPI_KEY:
        logger.info("Google Jobs (SerpAPI): no API key, skipping.")
        return []

    results = []
    try:
        from serpapi import GoogleSearch  # type: ignore
    except ImportError:
        logger.warning("google-search-results not installed. Run: pip install google-search-results")
        return []

    query = keywords
    if remote:
        query += " remote"
    if location not in query:
        query += f" {location}"

    params = {
        "engine": "google_jobs",
        "q": query,
        "hl": "en",
        "api_key": config.SERPAPI_KEY,
        "num": min(limit, 10),
    }

    try:
        search = GoogleSearch(params)
        data = search.get_dict()
        jobs = data.get("jobs_results", [])
        for job in jobs[:limit]:
            results.append(JobResult(
                company=job.get("company_name", "Unknown"),
                position=job.get("title", "Unknown"),
                location=job.get("location", location),
                link=job.get("share_link", job.get("job_id", "")),
                snippet=job.get("description", "")[:500],
                source="Google Jobs",
                salary=str(job.get("detected_extensions", {}).get("salary", "")),
                posted=str(job.get("detected_extensions", {}).get("posted_at", "")),
            ))
    except Exception as e:
        logger.warning("SerpAPI error: %s", e)

    logger.info("Google Jobs (SerpAPI): found %d results", len(results))
    return results


def search_google_scrape(
    keywords: str,
    location: str,
    remote: bool = False,
    limit: int = 15,
) -> list[JobResult]:
    """Scrape Google Jobs search results page (no API key needed, best-effort)."""
    results = []
    query = f"{keywords} jobs {location}"
    if remote:
        query += " remote"

    url = "https://www.google.com/search"
    params = {"q": query, "ibp": "htl;jobs", "hl": "en"}

    resp = _get(url, params=params)
    if not resp:
        return results

    soup = BeautifulSoup(resp.text, "lxml")

    # Google Jobs often renders in a special widget
    job_cards = soup.select("li.iFjolb") or soup.select("div.pE8vnd")
    for card in job_cards[:limit]:
        try:
            title = (card.select_one("div.BjJfJf") or card.select_one("div[class*='title']"))
            company = (card.select_one("div.vNEEBe") or card.select_one("div[class*='company']"))
            loc = card.select_one("div.Qk80Jf") or card.select_one("div[class*='location']")
            results.append(JobResult(
                company=company.get_text(strip=True) if company else "Unknown",
                position=title.get_text(strip=True) if title else "Unknown",
                location=loc.get_text(strip=True) if loc else location,
                link="",
                snippet="",
                source="Google Jobs",
            ))
        except Exception as e:
            logger.debug("Google Jobs card error: %s", e)

    logger.info("Google Jobs (scrape): found %d results", len(results))
    return results


# ── LinkedIn scraper (public listings) ───────────────────────────────────────

def search_linkedin(
    keywords: str,
    location: str,
    remote: bool = False,
    limit: int = 20,
) -> list[JobResult]:
    """Scrape LinkedIn public job listings (no login)."""
    results = []

    # LinkedIn's public jobs search URL
    geoId = "101686882"  # Kenya geo ID
    if "kenya" not in location.lower():
        geoId = ""

    url = "https://www.linkedin.com/jobs/search/"
    params = {
        "keywords": keywords,
        "location": location,
        "f_TPR": "r86400",  # Last 24 hours
        "start": "0",
    }
    if remote:
        params["f_WT"] = "2"  # Remote filter

    resp = _get(url, params=params)
    if not resp:
        logger.warning("LinkedIn: no response")
        return results

    soup = BeautifulSoup(resp.text, "lxml")
    cards = soup.select("div.base-card") or soup.select("li.jobs-search-results__list-item")

    for card in cards[:limit]:
        try:
            title_el = card.select_one("h3.base-search-card__title, h3 a")
            company_el = card.select_one("h4.base-search-card__subtitle a, h4 a")
            location_el = card.select_one("span.job-search-card__location")
            link_el = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
            snippet_el = card.select_one("p.job-search-card__snippet")

            title = title_el.get_text(strip=True) if title_el else "Unknown"
            company = company_el.get_text(strip=True) if company_el else "Unknown"
            loc = location_el.get_text(strip=True) if location_el else location
            link = link_el["href"].split("?")[0] if link_el and link_el.get("href") else ""
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""

            if title and company:
                results.append(JobResult(
                    company=company,
                    position=title,
                    location=loc,
                    link=link,
                    snippet=snippet,
                    source="LinkedIn",
                ))
        except Exception as e:
            logger.debug("LinkedIn card parse error: %s", e)

    logger.info("LinkedIn: found %d results for '%s'", len(results), keywords)
    return results


# ── Main search function ──────────────────────────────────────────────────────

def search_jobs(
    keywords: str | None = None,
    location: str | None = None,
    remote: bool | None = None,
    sources: list[str] | None = None,
    limit_per_source: int = 20,
    deduplicate_against_db: bool = True,
) -> list[JobResult]:
    """
    Search for jobs across all configured sources.

    Args:
        keywords:  e.g. "Python developer"
        location:  e.g. "Nairobi, Kenya"
        remote:    include remote jobs
        sources:   list of source names: ["indeed", "google", "linkedin"]
        limit_per_source: max results per source
        deduplicate_against_db: skip jobs already in applications.db

    Returns:
        Combined, deduplicated list of JobResult objects.
    """
    kw = keywords or config.JOB_KEYWORDS
    loc = location or config.JOB_LOCATION
    rem = remote if remote is not None else config.JOB_REMOTE
    srcs = sources or config.JOB_DISCOVERY_SOURCES

    all_results: list[JobResult] = []

    for source in srcs:
        _sleep(1.0, 2.5)
        if source == "indeed":
            all_results.extend(search_indeed(kw, loc, rem, limit_per_source))
        elif source == "google":
            if config.SERPAPI_KEY:
                all_results.extend(search_google_serpapi(kw, loc, rem, limit_per_source))
            else:
                all_results.extend(search_google_scrape(kw, loc, rem, limit_per_source))
        elif source == "linkedin":
            all_results.extend(search_linkedin(kw, loc, rem, limit_per_source))

    # Deduplicate within this batch by (company, position)
    seen = set()
    unique: list[JobResult] = []
    for job in all_results:
        key = (job.company.lower().strip(), job.position.lower().strip())
        if key not in seen:
            seen.add(key)
            unique.append(job)

    # Deduplicate against existing DB if requested
    if deduplicate_against_db:
        try:
            import django
            from core.models import JobApplication
            existing = {
                (a.company.lower().strip(), a.position.lower().strip())
                for a in JobApplication.objects.all()
            }
            unique = [j for j in unique if (j.company.lower().strip(), j.position.lower().strip()) not in existing]
        except Exception as e:
            logger.debug("DB dedup skipped: %s", e)

    logger.info(
        "Job search complete: %d unique new results (sources: %s)",
        len(unique), ", ".join(srcs),
    )
    return unique


def fetch_job_description(url: str) -> str:
    """
    Scrape the job description text from a given URL.
    Returns plain text (best effort).
    """
    resp = _get(url)
    if not resp:
        return ""
    soup = BeautifulSoup(resp.text, "lxml")

    # Remove nav, header, footer noise
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    # Common JD containers
    jd_el = (
        soup.select_one("div#jobDescriptionText")          # Indeed
        or soup.select_one("div.show-more-less-html__markup")  # LinkedIn
        or soup.select_one("div[class*='job-description']")
        or soup.select_one("div[class*='jobDescription']")
        or soup.select_one("section[class*='description']")
        or soup.find("article")
        or soup.find("main")
    )

    text = jd_el.get_text(separator="\n", strip=True) if jd_el else soup.get_text(separator="\n", strip=True)
    # Truncate to 3000 chars to stay within AI prompt limits
    return text[:3000].strip()


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Job Discovery CLI")
    parser.add_argument("--keywords", default=config.JOB_KEYWORDS)
    parser.add_argument("--location", default=config.JOB_LOCATION)
    parser.add_argument("--sources", nargs="+", default=config.JOB_DISCOVERY_SOURCES,
                        choices=["indeed", "google", "linkedin"])
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--no-dedup", action="store_true")
    args = parser.parse_args()

    jobs = search_jobs(
        keywords=args.keywords,
        location=args.location,
        sources=args.sources,
        limit_per_source=args.limit,
        deduplicate_against_db=not args.no_dedup,
    )

    print(f"\n{'='*60}")
    print(f"Found {len(jobs)} new job(s):")
    print(f"{'='*60}")
    for i, j in enumerate(jobs, 1):
        print(f"\n{i}. [{j.source}] {j.position} @ {j.company}")
        print(f"   Location : {j.location}")
        if j.salary:
            print(f"   Salary   : {j.salary}")
        print(f"   Link     : {j.link}")
        if j.snippet:
            print(f"   Summary  : {j.snippet[:120]}...")
