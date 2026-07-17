# Langfuse Tracing

Langfuse gives you **per-request LLM tracing** — for every chat message you can see the
full nested trace: the supervisor's routing decision, the hybrid retrieval, and each LLM
call with its prompt, completion, token usage, latency, and estimated cost. It
complements Prometheus/Grafana (which show aggregate operational metrics) with
request-level detail you can drill into when debugging a bad answer.

It is **optional and off by default** — the app runs fine without it.

## Enable it (free, ~2 minutes)

1. Create a free account and project at <https://cloud.langfuse.com> (or self-host).
2. In the project, go to **Settings → API Keys** and create a key pair.
3. In your `.env`:
   ```
   LANGFUSE_TRACING_ENABLED=true
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   LANGFUSE_HOST=https://cloud.langfuse.com
   ```
4. Restart the API: `docker compose restart api`.

Confirm it initialised — the logs will show a `langfuse_tracing_enabled` line with the
detected version:
```bash
docker compose logs api | grep langfuse
```

## Use it

Send a few chat messages, then open your Langfuse project. Each request appears as one
trace named after the graph run. Click a trace to see:

- the **routing** step and which specialist the supervisor chose,
- the **retrieval** span (for knowledge answers),
- every **LLM generation** with prompt, output, tokens, latency, and cost,
- any **fallback** to a secondary provider.

Traces are grouped by **session** and **user** (we pass `langfuse_session_id` and
`langfuse_user_id` as metadata), so you can follow a whole multi-turn conversation or
filter to one user.

## Correlating traces with logs

Every trace's metadata also includes `request_id` — the same id bound to every
structlog line for that request and echoed as the `x-request-id` response header
(both from `ContextLoggingMiddleware`). To jump from a log line (or a client-reported
request id) to its exact trace, filter Langfuse by that `request_id` metadata value.

## How it's wired (for reference)

`app/core/tracing.py` builds a LangChain `CallbackHandler` (supporting both Langfuse v2
and v3+ — the same code path also covers v4, which is what a fresh install resolves to
today since `langfuse>=2.53.0` has no upper bound). `app/api/v1/endpoints/chat.py`
attaches it once at the top-level graph invocation:

```python
config = {
    "configurable": {"thread_id": session_id},
    "callbacks": get_callbacks(),        # [] when disabled — a no-op
    "metadata": {
        "langfuse_session_id": session_id,
        "langfuse_user_id": user.id,
        "route_hint": "chat",
        "request_id": structlog.contextvars.get_contextvars().get("request_id"),
    },
}
final = await graph_manager.graph.ainvoke(initial, config=config)
```

Because LangGraph propagates the callback to every nested runnable, one attachment
point traces the entire graph — no per-node changes needed. When tracing is disabled,
`get_callbacks()` returns `[]`, so the same code path runs with zero overhead.

On shutdown, `app/main.py`'s `lifespan()` calls `tracing.flush()` after the graph
checkpointer closes. Langfuse batches events client-side, so a bare process exit can
drop traces for the last few in-flight requests — flushing first avoids that. The
flush is bounded to 5s (`app/core/tracing.py`'s `_FLUSH_TIMEOUT_S`): if the Langfuse
host is unreachable at shutdown, we log a warning and let the process exit anyway
rather than stall past the orchestrator's stop grace period (Docker's default is 10s).

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| No traces appear | Confirm `LANGFUSE_TRACING_ENABLED=true` and both keys are set; check `docker compose logs api \| grep langfuse` for an init warning. |
| `langfuse_enabled_but_keys_missing` in logs | One of the keys is blank in `.env`. |
| `langfuse_init_failed` in logs | Version/import mismatch — ensure `langfuse` (and, for v3+, the `langchain` package itself, not just `langchain-core`) is installed in the container (`docker compose exec api pip show langfuse langchain`). |
| `langfuse_flush_timeout` in logs on shutdown | Langfuse host was unreachable within 5s at shutdown — the last few traces for that run may be missing; the process still exits promptly. |
| Traces show but no token counts | Some free-tier providers don't return usage; latency/spans still appear. |
