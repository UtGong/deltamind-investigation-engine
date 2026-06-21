#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE=".env"
ENV_BACKUP=".env.eval_backup"

SERVER_BASE_URL="${SERVER_BASE_URL:-http://127.0.0.1:8000}"
API_BASE_URL="${API_BASE_URL:-${SERVER_BASE_URL}/api/v1}"
API_HEALTH_URL="${API_BASE_URL}/system/status"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

LOG_FILE="data/eval/eval_server.log"
PREDICTIONS_FILE="${PREDICTIONS_FILE:-data/eval/predictions.jsonl}"
REPORT_FILE="${REPORT_FILE:-data/eval/reports/latest_eval_report.md}"

mkdir -p data/eval/reports

restore_env() {
  if [ -f "$ENV_BACKUP" ]; then
    mv "$ENV_BACKUP" "$ENV_FILE"
  fi
}

cleanup() {
  if [ -n "${SERVER_PID:-}" ]; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
  fi
  restore_env
}

trap cleanup EXIT

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing .env file at backend/.env"
  exit 1
fi

cp "$ENV_FILE" "$ENV_BACKUP"

if grep -q "^DEV_LLM_FALLBACK_ENABLED=" "$ENV_FILE"; then
  sed -i 's/^DEV_LLM_FALLBACK_ENABLED=.*/DEV_LLM_FALLBACK_ENABLED=true/' "$ENV_FILE"
else
  echo "DEV_LLM_FALLBACK_ENABLED=true" >> "$ENV_FILE"
fi

echo "Starting local backend with DEV_LLM_FALLBACK_ENABLED=true..."
pkill -f "uvicorn app.main:app" >/dev/null 2>&1 || true

python -m uvicorn app.main:app --host "$HOST" --port "$PORT" > "$LOG_FILE" 2>&1 &
SERVER_PID=$!

echo "Backend PID: $SERVER_PID"
echo "Waiting for backend health..."

READY=false

for i in {1..40}; do
  if curl -fsS "$API_HEALTH_URL" >/dev/null 2>&1; then
    READY=true
    break
  fi

  if ! kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    echo "Backend failed to start. Log:"
    cat "$LOG_FILE"
    exit 1
  fi

  sleep 0.5
done

if [ "$READY" != "true" ]; then
  echo "Backend did not become ready. Log:"
  cat "$LOG_FILE"
  exit 1
fi

echo "Backend is ready."
sleep 1

echo "Running PIVOT eval..."
python scripts/run_pivot_eval_api.py \
  --input data/eval/gold_claims.jsonl \
  --output "$PREDICTIONS_FILE" \
  --base-url "$API_BASE_URL"

SUMMARY_FILE="${PREDICTIONS_FILE%.jsonl}.summary.json"

if [ -f "scripts/generate_pivot_eval_report.py" ]; then
  echo "Generating Markdown report..."
  python scripts/generate_pivot_eval_report.py \
    --predictions "$PREDICTIONS_FILE" \
    --summary "$SUMMARY_FILE" \
    --output "$REPORT_FILE" \
    --title "PIVOT Local Eval Report"

  echo "Report: $REPORT_FILE"
else
  echo "Report generator not found; skipping Markdown report."
fi

echo
echo "Eval summary:"
cat "$SUMMARY_FILE"
