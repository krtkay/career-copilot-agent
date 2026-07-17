"""Live job-search tool — Adzuna Jobs API.

Adzuna aggregates real job listings across many countries. The free tier needs an
``app_id`` + ``app_key`` (register at https://developer.adzuna.com). This is the
load-bearing external tool for the copilot: "find me python jobs in London" *is*
this call. If credentials are missing the tool returns a clear setup message rather
than failing, so the app still runs for anyone who hasn't registered yet.

Endpoint:
    GET https://api.adzuna.com/v1/api/jobs/{country}/search/{page}
        ?app_id=...&app_key=...&what=...&where=...&results_per_page=...
"""

from __future__ import annotations

import httpx
from langchain_core.tools import tool

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_BASE = "https://api.adzuna.com/v1/api/jobs/{country}/search/1"


def _fmt_salary(job: dict) -> str:
    lo, hi = job.get("salary_min"), job.get("salary_max")
    if not lo and not hi:
        return "salary not listed"
    predicted = " (estimated)" if job.get("salary_is_predicted") in (1, "1") else ""
    if lo and hi and lo != hi:
        return f"{lo:,.0f}–{hi:,.0f}{predicted}"
    return f"{(lo or hi):,.0f}{predicted}"


@tool
async def search_jobs(
    query: str = "", location: str = "", country: str = "", max_results: int = 5
) -> str:
    """Search real, current job listings by keyword and location.

    Use this whenever the user wants to find or browse jobs (e.g. "find remote python
    jobs in Berlin", "data analyst roles in New York"). ``query`` is the role/keywords,
    ``location`` is a city or region, ``country`` is a 2-letter code (gb, us, in, de,
    ca, au, ...). Returns a short list of matching roles with company, location, salary
    and a link to apply.
    """
    query = (query or "").strip()
    if not query:
        return "Please tell me what kind of role to search for (e.g. 'data analyst')."

    country = (country or settings.adzuna_default_country or "gb").lower().strip()
    app_id = settings.adzuna_app_id.get_secret_value()
    app_key = settings.adzuna_app_key.get_secret_value()
    if not app_id or not app_key:
        return (
            "Job search isn't configured yet: set ADZUNA_APP_ID and ADZUNA_APP_KEY in "
            ".env (free at https://developer.adzuna.com). I can still help with resume, "
            "interview, and salary questions in the meantime."
        )

    params = {
        "app_id": app_id,
        "app_key": app_key,
        "what": query,
        "results_per_page": max(1, min(max_results, 10)),
        "content-type": "application/json",
    }
    if location.strip():
        params["where"] = location.strip()

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(_BASE.format(country=country), params=params)
            if r.status_code == 401:
                return "Job search credentials were rejected — check ADZUNA_APP_ID/KEY."
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as exc:
        logger.warning("adzuna_http_error", error=str(exc))
        return "The job search service is unavailable right now. Please try again shortly."

    results = data.get("results", [])
    if not results:
        loc = f" in {location}" if location.strip() else ""
        return f"I didn't find any '{query}' jobs{loc} right now. Try broader terms."

    count = data.get("count")
    lines = [f"Found {count:,} '{query}' listings. Top {len(results)}:" if count else "Top matches:"]
    for i, job in enumerate(results, 1):
        company = (job.get("company") or {}).get("display_name", "Unknown company")
        loc = (job.get("location") or {}).get("display_name", "")
        title = job.get("title", "Role").replace("\n", " ").strip()
        lines.append(
            f"{i}. {title} — {company} ({loc})\n"
            f"   Salary: {_fmt_salary(job)}\n"
            f"   Apply: {job.get('redirect_url', 'n/a')}"
        )
    return "\n".join(lines)
