"""Salary insight tool — Adzuna salary/histogram data.

Gives a realistic pay range for a role in a country, which is exactly what the KB's
salary-negotiation advice tells users to research. Uses Adzuna's histogram endpoint
(annual amounts in the country's local currency).

Endpoint:
    GET https://api.adzuna.com/v1/api/jobs/{country}/histogram
        ?app_id=...&app_key=...&what=...
"""

from __future__ import annotations

import httpx
from langchain_core.tools import tool

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_HIST = "https://api.adzuna.com/v1/api/jobs/{country}/histogram"


@tool
async def get_salary_insights(role: str = "", country: str = "") -> str:
    """Get a realistic salary range for a job title in a country.

    Use this when the user asks what a role pays or wants data to prepare for salary
    negotiation (e.g. "what does a product manager earn in the UK?"). ``role`` is the
    job title; ``country`` is a 2-letter code (gb, us, in, de, ...). Figures are annual
    amounts in the country's local currency from real listings.
    """
    role = (role or "").strip()
    if not role:
        return "Please give me a job title to look up (e.g. 'software engineer')."

    country = (country or settings.adzuna_default_country or "gb").lower().strip()
    app_id = settings.adzuna_app_id.get_secret_value()
    app_key = settings.adzuna_app_key.get_secret_value()
    if not app_id or not app_key:
        return (
            "Salary lookup isn't configured: set ADZUNA_APP_ID and ADZUNA_APP_KEY in "
            ".env (free at https://developer.adzuna.com)."
        )

    params = {"app_id": app_id, "app_key": app_key, "what": role,
              "content-type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(_HIST.format(country=country), params=params)
            if r.status_code == 401:
                return "Salary credentials were rejected — check ADZUNA_APP_ID/KEY."
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as exc:
        logger.warning("adzuna_salary_http_error", error=str(exc))
        return "The salary service is unavailable right now. Please try again shortly."

    hist = data.get("histogram", {})
    if not hist:
        return f"I couldn't find salary data for '{role}' in {country.upper()}."

    # histogram maps salary-bucket -> count of jobs; derive a weighted picture.
    buckets = sorted((int(k), v) for k, v in hist.items())
    total = sum(v for _, v in buckets)
    if total == 0:
        return f"I couldn't find salary data for '{role}' in {country.upper()}."
    lo = buckets[0][0]
    hi = buckets[-1][0]
    weighted_avg = sum(k * v for k, v in buckets) / total
    # Modal bucket (most common salary band).
    modal = max(buckets, key=lambda kv: kv[1])[0]

    return (
        f"Salary insight for '{role}' in {country.upper()} (annual, local currency, "
        f"from {total:,} listings):\n"
        f"- Typical range: {lo:,.0f} to {hi:,.0f}\n"
        f"- Most common band starts around: {modal:,.0f}\n"
        f"- Weighted average: {weighted_avg:,.0f}\n"
        "Use the range as your negotiation anchor; aim near the upper end if your "
        "experience matches the role well."
    )
