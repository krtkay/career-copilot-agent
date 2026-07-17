#!/bin/sh
# Render's dockerCommand doesn't reliably interpret shell operators embedded
# directly in the command string (an inline "cmd1 && cmd2" was seen executing
# as one literal, non-existent command name instead of two commands) — so
# this logic lives in an actual script file instead. Invoked as `sh render-start.sh`
# from render.yaml, which sidesteps needing the execute bit set too.
set -e
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
