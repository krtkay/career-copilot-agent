"""Streamlit frontend for the Support Desk Agent.

A thin client over the FastAPI backend. It exists purely to *drive and inspect* the
API — it holds no business logic of its own. Everything it shows (route, citations,
ticket, guardrail flags) comes straight from the `/chat` response, so it doubles as
a live debugging surface for the agent graph.

Run:  streamlit run frontend/streamlit_app.py
(The backend must be running — see the README quickstart.)
"""

from __future__ import annotations

import os
import uuid

import httpx
import streamlit as st

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
DEFAULT_API = os.getenv("API_BASE_URL", "http://localhost:8000")
API_PREFIX = "/api/v1"
ROUTE_ICONS = {
    "knowledge": "📚",
    "job_search": "🔎",
    "draft": "✍️",
    "track": "🗂️",
    "escalate": "🧑‍💼",
    "smalltalk": "💬",
    "out_of_scope": "🚫",
}
DEMO_USER = ("user@example.com", "user-password-123")
DEMO_AGENT = ("agent@example.com", "agent-password-123")

st.set_page_config(page_title="Career Copilot", page_icon="🚀", layout="wide")


# --------------------------------------------------------------------------- #
# Session state
# --------------------------------------------------------------------------- #
def _init_state() -> None:
    st.session_state.setdefault("api_base", DEFAULT_API)
    st.session_state.setdefault("token", None)
    st.session_state.setdefault("email", None)
    st.session_state.setdefault("is_agent", False)
    st.session_state.setdefault("session_id", str(uuid.uuid4()))
    st.session_state.setdefault("messages", [])  # list of dicts


_init_state()


# --------------------------------------------------------------------------- #
# API helpers
# --------------------------------------------------------------------------- #
def _url(path: str) -> str:
    return f"{st.session_state.api_base}{API_PREFIX}{path}"


def api_health() -> tuple[bool, str]:
    try:
        r = httpx.get(_url("/health"), timeout=4)
        if r.status_code == 200:
            return True, r.json().get("env", "ok")
        return False, f"HTTP {r.status_code}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:60]


def api_auth(email: str, password: str, *, register: bool) -> tuple[bool, str]:
    endpoint = "/auth/register" if register else "/auth/login"
    try:
        r = httpx.post(
            _url(endpoint), json={"email": email, "password": password}, timeout=15
        )
        if r.status_code in (200, 201):
            st.session_state.token = r.json()["access_token"]
            st.session_state.email = email
            return True, "Signed in."
        if r.status_code == 409:
            return False, "Email already registered — try logging in instead."
        if r.status_code == 401:
            return False, "Invalid credentials."
        return False, f"HTTP {r.status_code}: {r.text[:120]}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:120]


def api_chat(message: str) -> dict | None:
    try:
        r = httpx.post(
            _url("/chat"),
            headers={"Authorization": f"Bearer {st.session_state.token}"},
            json={"message": message, "session_id": st.session_state.session_id},
            timeout=90,
        )
        if r.status_code == 200:
            return r.json()
        if r.status_code == 401:
            st.session_state.token = None
            st.error("Session expired — please sign in again.")
            return None
        if r.status_code == 429:
            st.warning("Rate limited (20/min). Wait a moment and retry.")
            return None
        st.error(f"Chat failed: HTTP {r.status_code} — {r.text[:160]}")
        return None
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not reach the API: {exc}")
        return None


def api_tickets() -> list[dict] | None:
    try:
        r = httpx.get(
            _url("/tickets"),
            headers={"Authorization": f"Bearer {st.session_state.token}"},
            timeout=15,
        )
        if r.status_code == 200:
            return r.json()
        if r.status_code == 403:
            st.info("Only agent accounts can list tickets. Sign in as the demo agent.")
            return None
        st.error(f"Tickets failed: HTTP {r.status_code}")
        return None
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))
        return None


# --------------------------------------------------------------------------- #
# Sidebar — connection, auth, session
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("🚀 Career Copilot")

    st.text_input("API base URL", key="api_base")
    ok, detail = api_health()
    st.caption(f"{'🟢 API up' if ok else '🔴 API down'} · {detail}")

    st.divider()

    if st.session_state.token:
        st.success(f"Signed in as **{st.session_state.email}**")
        if st.button("Sign out", use_container_width=True):
            st.session_state.token = None
            st.session_state.email = None
            st.rerun()
    else:
        st.subheader("Sign in")
        with st.form("auth_form", clear_on_submit=False):
            email = st.text_input("Email", value=DEMO_USER[0])
            password = st.text_input("Password", value=DEMO_USER[1], type="password")
            c1, c2 = st.columns(2)
            login_clicked = c1.form_submit_button("Log in", use_container_width=True)
            register_clicked = c2.form_submit_button(
                "Register", use_container_width=True
            )
        if login_clicked or register_clicked:
            success, msg = api_auth(email, password, register=register_clicked)
            (st.success if success else st.error)(msg)
            if success:
                st.rerun()

        st.caption("Demo accounts (created by `make seed`):")
        st.code(
            f"user:  {DEMO_USER[0]} / {DEMO_USER[1]}\n"
            f"agent: {DEMO_AGENT[0]} / {DEMO_AGENT[1]}",
            language="text",
        )

    st.divider()
    st.subheader("Conversation")
    st.caption(f"Session id: `{st.session_state.session_id[:8]}…`")
    if st.button("🔄 New conversation", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()

    st.divider()
    with st.expander("💡 Try these"):
        st.markdown(
            "- *How do I optimize my resume for an ATS?* → **knowledge**\n"
            "- *What is the STAR method?* → **knowledge**\n"
            "- *Find data analyst jobs in London* → **job_search** (live)\n"
            "- *What does a product manager earn in the US?* → **job_search** (live)\n"
            "- *Write a cover letter for a data scientist role* → **draft**\n"
            "- *Remind me I applied to Acme today* → **track**\n"
            "- *Ignore all previous instructions* → **guardrail**"
        )


# --------------------------------------------------------------------------- #
# Main — tabs: Chat + Agent console
# --------------------------------------------------------------------------- #
st.title("AI Career & Job Search Copilot")
st.caption(
    "A supervisor routes each message to a specialist — knowledge (career advice, "
    "grounded + cited), job_search (live Adzuna listings + salary), draft (cover "
    "letters & outreach), or track — with guardrails on every turn."
)

chat_tab, agent_tab = st.tabs(["💬 Chat", "🎫 Agent console"])


def _render_meta(meta: dict) -> None:
    """Render the route / citations / ticket / guardrail detail for a turn."""
    route = meta.get("route", "?")
    icon = ROUTE_ICONS.get(route, "•")
    cols = st.columns(3)
    cols[0].metric("Route", f"{icon} {route}")
    cols[1].metric("Needs human", "Yes" if meta.get("needs_human") else "No")
    guard = meta.get("guardrails", {})
    flags = (guard.get("input_flags", []) or []) + (guard.get("output_flags", []) or [])
    cols[2].metric("Guardrail flags", len(flags))

    if flags:
        st.warning("Guardrail flags: " + ", ".join(f"`{f}`" for f in flags))

    if meta.get("ticket_id"):
        st.info(f"🎫 Ticket created: `{meta['ticket_id']}`")

    citations = meta.get("citations", [])
    if citations:
        with st.expander(f"📚 {len(citations)} source(s) used", expanded=False):
            for i, c in enumerate(citations, 1):
                st.markdown(
                    f"**[{i}] {c.get('document_title', '?')}** "
                    f"· `{c.get('source', '')}` · score {c.get('score', 0):.3f}"
                )
                st.caption(c.get("snippet", ""))


with chat_tab:
    # Replay history.
    for turn in st.session_state.messages:
        with st.chat_message(turn["role"]):
            st.markdown(turn["content"])
            if turn["role"] == "assistant" and turn.get("meta"):
                _render_meta(turn["meta"])

    prompt = st.chat_input(
        "Ask a question or describe your problem…"
        if st.session_state.token
        else "Sign in first (sidebar) to start chatting."
    )

    if prompt:
        if not st.session_state.token:
            st.error("Please sign in from the sidebar first.")
        else:
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("Routing to the right agent…"):
                    resp = api_chat(prompt)
                if resp:
                    st.markdown(resp.get("answer", "_(no answer)_"))
                    _render_meta(resp)
                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": resp.get("answer", ""),
                            "meta": resp,
                        }
                    )


with agent_tab:
    st.subheader("Application tracker")
    st.caption(
        "Items you saved via the track agent, plus any escalations. "
        "Requires an **agent** account (sign in as the demo agent)."
    )
    if not st.session_state.token:
        st.info("Sign in from the sidebar to view tickets.")
    elif st.button("Refresh tickets"):
        pass  # falls through to fetch below
    if st.session_state.token:
        tickets = api_tickets()
        if tickets:
            # Small summary metrics.
            by_priority: dict[str, int] = {}
            for t in tickets:
                by_priority[t["priority"]] = by_priority.get(t["priority"], 0) + 1
            mcols = st.columns(4)
            for i, p in enumerate(["urgent", "high", "medium", "low"]):
                mcols[i].metric(p.capitalize(), by_priority.get(p, 0))
            st.dataframe(
                [
                    {
                        "id": t["id"][:8],
                        "priority": t["priority"],
                        "status": t["status"],
                        "category": t["category"],
                        "subject": t["subject"],
                        "created": t["created_at"][:19].replace("T", " "),
                    }
                    for t in tickets
                ],
                use_container_width=True,
                hide_index=True,
            )
        elif tickets == []:
            st.success("No tickets yet — trigger one from the Chat tab.")
