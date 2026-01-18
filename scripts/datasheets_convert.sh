#!/usr/bin/env bash
set -euo pipefail

# Convert a PDF into the datasheets repository structure:
# - store source PDF under datasheets/manufacturers/<mfr>/<doc-id>/source/
# - generate outputs:
#   - outputs/pdftotext/ (baseline)
#   - outputs/pdf2md/auto/
#   - outputs/pdf2md/always/
#
# NOTE: Do NOT use this for confidential / NDA / proprietary documents.

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

DATASHEETS_DIR="${DATASHEETS_DIR:-$REPO_DIR/datasheets}"

MFR=""
DOC_ID=""
PDF_PATH=""
PROVIDER="${PROVIDER:-anthropic}"  # anthropic|gemini
WORKERS="${WORKERS:-2}"
LLM_RPS="${LLM_RPS:-0.5}"
ALSO_ALWAYS=0
FORCE=0
EXTRA_ARGS=()

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/datasheets_convert.sh --manufacturer <mfr> --doc-id <id> --pdf <path> [options]

Required:
  --manufacturer <mfr>     Manufacturer folder name (e.g., nxp)
  --doc-id <id>            Document id (e.g., AN13917)
  --pdf <path>             Path to the source PDF

Options:
  --provider anthropic|gemini   (default: anthropic)
  --workers N                   (default: 2)
  --llm-rps N                   (default: 0.5)
  --force                       Overwrite existing outputs (disable resume for pdf2md runs)
  --also-always                 Also generate pdf2md always-vision output (default: off)
  --datasheets-dir PATH         (default: ./datasheets)
  --                            Pass remaining args through to pdf2md.py (e.g. --pages "9")
  -h, --help                    Show help

Environment (commonly used):
  LLM_PROVIDER, ANTHROPIC_API_KEY / GOOGLE_API_KEY, model vars, etc.

Notes:
  - If you pass through `--pages ...` to `pdf2md.py`, this script switches to **PAGE TEST MODE**:
    - outputs are written under `outputs/page_tests/<mfr>/<doc-id>/...` (git-ignored)
    - the `datasheets/` submodule is NOT modified
    - `pdftotext` baseline generation is skipped (faster/cheaper iteration)

This script writes into the datasheets repository for full runs. Only use for publicly distributable PDFs.
USAGE
}

extract_pages_spec() {
  local i=0
  while [[ $i -lt ${#EXTRA_ARGS[@]} ]]; do
    local a="${EXTRA_ARGS[$i]}"
    if [[ "$a" == "--pages" ]]; then
      # next arg is the spec
      echo "${EXTRA_ARGS[$((i+1))]:-}"
      return 0
    fi
    if [[ "$a" == --pages=* ]]; then
      echo "${a#--pages=}"
      return 0
    fi
    i=$((i+1))
  done
  return 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --manufacturer)
      MFR="${2:-}"; shift 2;;
    --doc-id)
      DOC_ID="${2:-}"; shift 2;;
    --pdf)
      PDF_PATH="${2:-}"; shift 2;;
    --provider)
      PROVIDER="${2:-}"; shift 2;;
    --workers)
      WORKERS="${2:-}"; shift 2;;
    --llm-rps)
      LLM_RPS="${2:-}"; shift 2;;
    --force)
      FORCE=1; shift 1;;
    --also-always)
      ALSO_ALWAYS=1; shift 1;;
    --datasheets-dir)
      DATASHEETS_DIR="${2:-}"; shift 2;;
    -h|--help)
      usage; exit 0;;
    --)
      shift
      EXTRA_ARGS+=("$@")
      break;;
    *)
      echo "Unknown arg: $1" >&2
      usage
      exit 2;;
  esac
done

if [[ -z "$MFR" || -z "$DOC_ID" || -z "$PDF_PATH" ]]; then
  echo "ERROR: --manufacturer, --doc-id, and --pdf are required." >&2
  usage
  exit 2
fi

if [[ ! -f "$PDF_PATH" ]]; then
  echo "ERROR: PDF not found: $PDF_PATH" >&2
  exit 2
fi

PAGES_SPEC="$(extract_pages_spec || true)"
PAGE_TEST_MODE=0
if [[ -n "${PAGES_SPEC:-}" ]]; then
  PAGE_TEST_MODE=1
  echo "NOTE: Detected --pages \"$PAGES_SPEC\" -> PAGE TEST MODE (outputs under ./outputs/page_tests; datasheets repo will not be modified)"
fi

if [[ "$PAGE_TEST_MODE" == "1" ]]; then
  DOC_DIR="$REPO_DIR/outputs/page_tests/$MFR/$DOC_ID"
else
  if [[ ! -d "$DATASHEETS_DIR" ]]; then
    echo "ERROR: datasheets directory not found at: $DATASHEETS_DIR" >&2
    echo "Did you initialize submodules? Try: git submodule update --init --recursive" >&2
    exit 2
  fi
  if ! command -v pdftotext >/dev/null 2>&1; then
    echo "ERROR: pdftotext not found in PATH. Install poppler-utils and retry." >&2
    exit 2
  fi
  DOC_DIR="$DATASHEETS_DIR/manufacturers/$MFR/$DOC_ID"
fi

SRC_DIR="$DOC_DIR/source"
OUT_BASE="$DOC_DIR/outputs"
OUT_TEXT="$OUT_BASE/pdftotext"
OUT_PDF2MD_AUTO="$OUT_BASE/pdf2md/auto"
OUT_PDF2MD_ALWAYS="$OUT_BASE/pdf2md/always"

mkdir -p "$SRC_DIR" "$OUT_TEXT" "$OUT_PDF2MD_AUTO"
if [[ "$ALSO_ALWAYS" == "1" ]]; then
  mkdir -p "$OUT_PDF2MD_ALWAYS"
fi

PDF_BASENAME="$(basename "$PDF_PATH")"
DEST_PDF="$SRC_DIR/$PDF_BASENAME"
cp -f "$PDF_PATH" "$DEST_PDF"

echo "Copied source PDF -> $DEST_PDF"

# Record checksum
if command -v sha256sum >/dev/null 2>&1; then
  (cd "$SRC_DIR" && sha256sum "$PDF_BASENAME" > SHA256SUMS.txt)
fi

# Create minimal README templates if missing (only for datasheets mode)
if [[ "$PAGE_TEST_MODE" != "1" && ! -f "$DOC_DIR/README.md" ]]; then
  cat > "$DOC_DIR/README.md" <<EOF
# $DOC_ID ($MFR) – Conversion Comparison

## Critical: public documents only

**Do not store confidential or NDA/proprietary datasheets here.** Only include documents you are allowed to redistribute publicly.

## Source
- Source PDF(s): \`source/\`

## Outputs
- Baseline: \`outputs/pdftotext/\`
- pdf2md auto: \`outputs/pdf2md/auto/\`
- pdf2md always: \`outputs/pdf2md/always/\`

## Comparison notes

Fill in accuracy observations vs the original PDF and between outputs.
EOF
fi

if [[ "$PAGE_TEST_MODE" != "1" ]]; then
  echo "Generating pdftotext baseline..."
  pdftotext -layout "$DEST_PDF" "$OUT_TEXT/output.txt"
fi

run_pdf2md_variant() {
  local variant="$1"   # auto|always
  local outdir="$2"
  local vision_env_key=""
  local vision_mode="$variant"

  if [[ "$PROVIDER" == "anthropic" ]]; then
    export LLM_PROVIDER="anthropic"
    vision_env_key="ANTHROPIC_VISION_MODE"
  else
    export LLM_PROVIDER="gemini"
    vision_env_key="LLM_VISION_MODE"
  fi

  if [[ "$variant" == "auto" ]]; then
    vision_mode="auto"
  else
    vision_mode="always"
  fi

  export "$vision_env_key"="$vision_mode"
  export LLM_RPS="$LLM_RPS"

  echo "Running pdf2md ($PROVIDER, vision=$vision_mode) -> $outdir"
  cmd=(python "$REPO_DIR/pdf2md.py" -i "$DEST_PDF" -o "$outdir" -p "$REPO_DIR/prompt.txt" -w "$WORKERS" --provider "$PROVIDER")
  if [[ "$FORCE" == "1" ]]; then
    cmd+=("--force")
  fi
  if [[ "${#EXTRA_ARGS[@]}" -gt 0 ]]; then
    cmd+=("${EXTRA_ARGS[@]}")
  fi
  "${cmd[@]}"
}

run_pdf2md_variant "auto" "$OUT_PDF2MD_AUTO"
if [[ "$ALSO_ALWAYS" == "1" ]]; then
  run_pdf2md_variant "always" "$OUT_PDF2MD_ALWAYS"
fi

if [[ "$PAGE_TEST_MODE" != "1" ]]; then
  # Rewrite output README metadata for full datasheets runs (idempotent; no LLM calls).
  python "$REPO_DIR/scripts/refresh_output_readmes.py" \
    --doc-dir "$DOC_DIR" \
    --provider "$PROVIDER" \
    --workers "$WORKERS" \
    --llm-rps "$LLM_RPS"
fi

echo "Done."
echo "Datasheet folder: $DOC_DIR"
