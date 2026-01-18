#!/usr/bin/env bash
set -euo pipefail

# Smoke test Anthropic support WITHOUT relying on .env.
#
# Usage (interactive, recommended):
#   ./scripts/smoke_test_anthropic.sh
#
# Usage (already have env var set):
#   ANTHROPIC_API_KEY=... ./scripts/smoke_test_anthropic.sh
#
# Offline mock mode (no network, no key required):
#   LLM_MOCK=1 ./scripts/smoke_test_anthropic.sh

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

export LLM_PROVIDER="${LLM_PROVIDER:-anthropic}"

# If a local .env exists, load it into the environment for this script run.
# This avoids prompting when ANTHROPIC_API_KEY is already present in .env.
ENV_FILE="${ENV_FILE:-$REPO_DIR/.env}"
if [[ -f "$ENV_FILE" ]]; then
  echo "Loading environment from: $ENV_FILE"
  # Temporarily disable nounset in case the env file contains references to unset vars.
  set +u
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  set -u
fi

if [[ "${LLM_MOCK:-}" == "1" ]]; then
  echo "Running in LLM_MOCK=1 (offline mock mode)"
fi

if [[ -z "${ANTHROPIC_API_KEY:-}" && "${LLM_MOCK:-}" != "1" ]]; then
  # Read from terminal without echo. Avoids shell history leakage from inline commands.
  if [[ -t 0 ]]; then
    read -r -s -p "Enter ANTHROPIC_API_KEY (input hidden): " ANTHROPIC_API_KEY
    echo
    export ANTHROPIC_API_KEY
  else
    echo "ERROR: ANTHROPIC_API_KEY is not set and stdin is not a TTY." >&2
    echo "Run interactively, or set ANTHROPIC_API_KEY in your environment." >&2
    exit 1
  fi
fi

python pdf2md.py --smoke-test --provider anthropic

