"""LangChain tools.

The job-search agent binds ``ACTION_TOOLS`` (real Adzuna API calls) so the model can
find live listings and salary data. ``search_knowledge_base`` is used directly by the
knowledge node for grounded career advice.
"""

from app.core.langgraph.tools.job_search import search_jobs
from app.core.langgraph.tools.kb_search import search_knowledge_base
from app.core.langgraph.tools.salary import get_salary_insights

# Live-data tools the job-search agent may call.
ACTION_TOOLS = [search_jobs, get_salary_insights]

TOOLS = [*ACTION_TOOLS, search_knowledge_base]

__all__ = [
    "TOOLS",
    "ACTION_TOOLS",
    "search_jobs",
    "get_salary_insights",
    "search_knowledge_base",
]
