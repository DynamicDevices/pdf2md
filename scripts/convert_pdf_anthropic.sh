#!/usr/bin/env bash
set -euo pipefail

# Convert a real PDF using Anthropic Claude (loads .env if present).
#
# Usage:
#   ./scripts/convert_pdf_anthropic.sh -i /path/to/manual.pdf -o outputs/manual
#
# Optional:
#   -p prompt file (default: prompt.txt)
#   -w max workers (default: 4)
#   --provider anthropic|gemini (default: anthropic)
#   --llm-rps N (optional request throttle; shared across workers)
#   --force (overwrite existing outputs; disable resume)
#   -- (pass-through any extra args to pdf2md.py)
#
# Examples:
#   ./scripts/convert_pdf_anthropic.sh -i manual.pdf -o output_md
#   ./scripts/convert_pdf_anthropic.sh -i manual.pdf -o output_md -w 8
#   ./scripts/convert_pdf_anthropic.sh -i manual.pdf -o output_md -p prompt.txt
#
# Notes:
# - This script will NOT print your API key.
# - If you prefer not to use .env, you can set ANTHROPIC_API_KEY in your environment.

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

ENV_FILE="${ENV_FILE:-$REPO_DIR/.env}"
if [[ -f "$ENV_FILE" ]]; then
  echo "Loading environment from: $ENV_FILE"
  set +u
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  set -u
fi

PDF_PATH=""
OUTPUT_DIR=""
PROMPT_FILE="prompt.txt"
MAX_WORKERS="4"
PROVIDER="${LLM_PROVIDER:-anthropic}"
LLM_RPS="${LLM_RPS:-}"
FORCE=0

EXTRA_ARGS=()

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/convert_pdf_anthropic.sh -i /path/to/manual.pdf -o outputs/manual [options] [-- extra pdf2md.py args]

Options:
  -i PATH    Input PDF file path (required)
  -o DIR     Output directory (required)
  -p PATH    Prompt template file (default: prompt.txt)
  -w N       Max workers (default: 4)
  --provider anthropic|gemini  (default: anthropic or LLM_PROVIDER)
  -h         Show help

Environment:
  - Loads .env from repo root if present (override with ENV_FILE=/path/to/.env)
  - For Anthropic: requires ANTHROPIC_API_KEY
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -i|--pdf)
      PDF_PATH="${2:-}"; shift 2;;
    -o|--output)
      OUTPUT_DIR="${2:-}"; shift 2;;
    -p|--prompt)
      PROMPT_FILE="${2:-}"; shift 2;;
    -w|--workers)
      MAX_WORKERS="${2:-}"; shift 2;;
    --provider)
      PROVIDER="${2:-}"; shift 2;;
    --llm-rps)
      LLM_RPS="${2:-}"; shift 2;;
    --force)
      FORCE=1; shift 1;;
    -h|--help)
      usage; exit 0;;
    --)
      shift
      EXTRA_ARGS+=("$@")
      break;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2;;
  esac
done

if [[ -z "$PDF_PATH" || -z "$OUTPUT_DIR" ]]; then
  echo "ERROR: -i and -o are required." >&2
  usage
  exit 2
fi

if [[ "${OUTPUT_DIR,,}" == *.md || "${OUTPUT_DIR,,}" == *.markdown ]]; then
  echo "ERROR: -o/--output must be a directory, but you provided what looks like a file: $OUTPUT_DIR" >&2
  echo "Use something like: -o IMX93RM_out" >&2
  exit 2
fi

if [[ ! -f "$PDF_PATH" ]]; then
  echo "ERROR: PDF not found: $PDF_PATH" >&2
  exit 2
fi

if [[ ! -f "$PROMPT_FILE" ]]; then
  echo "ERROR: Prompt file not found: $PROMPT_FILE" >&2
  exit 2
fi

if [[ "$PROVIDER" == "anthropic" ]]; then
  if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    echo "ERROR: ANTHROPIC_API_KEY is not set." >&2
    echo "Set it in .env, or export it in your shell, then re-run." >&2
    exit 2
  fi
fi

mkdir -p "$OUTPUT_DIR"

if ! python -c "import fitz" >/dev/null 2>&1; then
  echo "ERROR: Missing dependency PyMuPDF (module 'fitz') in the current Python environment." >&2
  echo "Install deps and retry:" >&2
  echo "  python -m pip install -r requirements.txt" >&2
  echo "Or:" >&2
  echo "  python -m pip install PyMuPDF" >&2
  exit 2
fi

echo "Running conversion:"
echo "  Provider:     $PROVIDER"
echo "  Input PDF:    $PDF_PATH"
echo "  Output dir:   $OUTPUT_DIR"
echo "  Prompt file:  $PROMPT_FILE"
echo "  Max workers:  $MAX_WORKERS"
if [[ -n "$LLM_RPS" ]]; then
  echo "  LLM RPS:      $LLM_RPS"
fi

python pdf2md.py \
  --provider "$PROVIDER" \
  -i "$PDF_PATH" \
  -o "$OUTPUT_DIR" \
  -p "$PROMPT_FILE" \
  -w "$MAX_WORKERS" \
  $([[ "$FORCE" == "1" ]] && echo "--force") \
  ${LLM_RPS:+--llm-rps "$LLM_RPS"} \
  "${EXTRA_ARGS[@]}"

