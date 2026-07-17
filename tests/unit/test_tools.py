"""Unit tests for the Adzuna tools' input-validation branches (offline)."""

from __future__ import annotations

from app.core.langgraph.tools.job_search import search_jobs
from app.core.langgraph.tools.salary import get_salary_insights


async def test_search_jobs_requires_query():
    out = await search_jobs.ainvoke({"query": "  "})
    assert "what kind of role" in out


async def test_salary_requires_role():
    out = await get_salary_insights.ainvoke({"role": ""})
    assert "job title" in out


def test_action_tools_registered():
    from app.core.langgraph.tools import ACTION_TOOLS

    names = {t.name for t in ACTION_TOOLS}
    assert names == {"search_jobs", "get_salary_insights"}
