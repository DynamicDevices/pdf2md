# Validation Plan (Embedded Datasheets / Reference Manuals)

This document defines how we validate conversion outputs over time so we can confidently say **what improved** or **what regressed**, with an emphasis on **embedded correctness**: tables, registers, GPIO/pin mux, and “no hallucinations”.

## Goals

- **No hallucinations**: never invent register values, bitfields, units, timings, addresses, or electrical specs.
- **Table correctness first**: preserve tables **exactly** (cells, numbers, units, headings).
- **Embedded usability**: GPIO/pin mux mappings and register access semantics must be trustworthy.
- **Comparability across runs**: make it easy to diff `pdftotext` vs `pdf2md` variants and track changes.

## Outputs to compare

For each source PDF, we keep:
- **Baseline**: `pdftotext -layout` output (raw, lowest-processing reference).
- **pdf2md auto**: `pdf2md` with `ANTHROPIC_VISION_MODE=auto` (or `LLM_VISION_MODE=auto` for Gemini).
- **pdf2md always** (optional): only when needed for diagram-heavy docs.

## Embedded criteria (quality gates)

### 1) No hallucination (hard gate)

**Fail** if any of these appear to be invented or modified:
- Hex literals / addresses / offsets (e.g. `0x4000_1000`)
- Bit ranges / bit positions (e.g. `[31:0]`, `7:4`)
- Numeric values with units (e.g. `3.3 V`, `125 °C`, `25 mA`, `100 ns`, `400 kHz`)
- Register field names / access types (RO/RW/W1C/etc.) if they don’t exist in the source text

**How to validate**
- **Automated**: run with `LLM_STRICT=1` (default). This rejects LLM outputs that introduce new “technical tokens”.
- **Manual**: spot-check a few sensitive tables (see “Sampling”).

### 2) Table correctness (hard gate for datasheets)

**Pass** only if tables are preserved with:
- Correct row/column count
- Correct headers
- Exact cell content (numbers + units + footnotes)
- No reordering, normalization, or “helpful” rewriting

**How to validate**
- **Automated**:
  - Table-first extraction creates:
    - Verbatim markdown tables (wrapped in `<!-- VERBATIM_TABLE_START --> ... <!-- VERBATIM_TABLE_END -->`)
    - Cropped table images (e.g. `images/page_<N>_table_<K>.png`)
  - Compare the markdown table to the cropped image for a handful of randomly chosen tables.
- **Manual**: spot-check at least the “most critical” tables (below).

### 3) Registers & GPIO/pin mux correctness (hard gate for reference manuals)

**Pass** only if:
- Register addresses/offsets match the PDF
- Bitfield names and bit ranges match
- Reset values match
- Access semantics (RW/RO/W1C, side-effects) are preserved verbatim
- GPIO alternate-function tables map correctly (pad ↔ mux mode ↔ signal name ↔ notes)

**How to validate**
- **Manual** (required): use the cropped table images and confirm:
  - at least 3 register-map tables
  - at least 2 GPIO/pin mux tables

### 4) Diagrams (soft gate, but important for usability)

**Pass** if:
- Diagram images are extracted and linked
- Captions match
- Descriptions are reasonable and do not introduce new hard technical values (covered by strict mode)

## Sampling strategy (what to check per document)

Minimum for each new converter change:
- **Tables**:
  - 2 electrical/timing/spec tables (units-heavy)
  - 2 register-map tables (bitfields-heavy)
  - 1 pin mux / GPIO table (mapping-heavy)
- **Code blocks / commands** (if present):
  - 1–2 sections with shell commands / scripts
- **Diagrams** (if present):
  - 1–2 key block diagrams (confirm links + caption)

## Comparison workflow (repeatable)

For a given datasheet folder (e.g. `datasheets/manufacturers/nxp/AN13917/`):

1. **Record metadata**
   - Source PDF checksum
   - `pdftotext -v`
   - `pdf2md` git SHA and whether it was dirty
   - Provider/model/vision mode, throttling, retry settings

2. **Sanity checks**
   - `pdf2md` outputs include `index.md`
   - `index.md` links resolve to actual files
   - `images/` exists and has expected figure/table crops

3. **Hard gates**
   - Confirm `LLM_STRICT=1` was enabled (or explicitly justified if disabled).
   - Spot-check the sampled tables vs cropped images.

4. **Diff & regression notes**
   - Compare `pdf2md/auto` vs previous `pdf2md/auto`:
     - table differences (should be none unless extraction improved)
     - added/removed sections
     - changes in headings / structure
   - Compare `pdf2md/auto` vs `pdftotext`:
     - ensure critical values aren’t missing or altered

## Scoring rubric (optional but useful)

Use this to summarize each run in the per-datasheet README:
- **No hallucination**: Pass/Fail (hard gate)
- **Tables**: Pass/Fail (hard gate for datasheets)
- **Registers/GPIO**: Pass/Fail (hard gate for ref manuals)
- **Structure/navigation**: 1–5
- **Diagram usability**: 1–5
- **Notes**: list any known defects and pages/sections affected

## “Regression signals” to watch for

- A table that used to be correct now has:
  - shifted columns
  - missing rows
  - changed numeric formatting or units
- A register map missing bit ranges or reset values
- Strict mode rejections increasing (could indicate worse extraction or prompt/provider behavior)
- More “empty” or truncated code blocks
- `index.md` links breaking (filename truncation/collisions)

## Future automation ideas (not required to proceed)

- A `scripts/validate_datasheet.py` that:
  - checks link integrity (`index.md`)
  - counts tables / table crops
  - flags strict-mode rejections
  - reports diffs in extracted tech tokens across runs

