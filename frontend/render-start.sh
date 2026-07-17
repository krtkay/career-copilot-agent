#!/bin/sh
# Streamlit needs to bind to Render's assigned $PORT (the Dockerfile's own CMD
# hardcodes 8501, which only works for local docker-compose). Kept as a script
# rather than an inline dockerCommand string for the same reason as
# ../render-start.sh: Render doesn't reliably interpret shell syntax embedded
# directly in the command string.
set -e
exec streamlit run frontend/streamlit_app.py \
  --server.port="${PORT:-8501}" \
  --server.address=0.0.0.0 \
  --server.headless=true
