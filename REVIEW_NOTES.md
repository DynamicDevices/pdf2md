# Project Review Notes (for discussion)

## Summary
The project’s overall architecture matches the stated goal: **ToC-based chunking + image extraction + LLM cleanup** produces AI-friendly, navigable Markdown for very large technical PDFs. The inclusion of **parallel formatting** and **resume-by-skipping existing section outputs** is a practical strength for long-running conversions.

This document captures **gaps/risks** and **proposed improvements** for discussion before making changes.

## Strengths
- **ToC-driven chunking**: good default for huge PDFs; yields semantically meaningful files.
- **Dual model approach** (vision vs text-only): good cost/perf tradeoff when many pages have no diagrams.
- **Resume capability**: skipping already-produced `.md` outputs supports safe restarts.
- **Backoff on rate limits**: basic exponential backoff improves robustness against 429/quota errors.

## Biggest gaps / risks (highest priority)

### Missing repo assets referenced by README
- README instructs users to copy `.env.example`, but the repository currently **does not include** `.env.example`.
  - Discussion: add `.env.example` and also add `.env` to `.gitignore`.

### Output filename collisions (silent overwrite risk)
- `sanitize_filename(title)` lowercases and truncates to 75 chars.
- Different titles can map to the same filename → risk of **overwriting sections** and producing incorrect `index.md` links.
  - Discussion: include a stable unique prefix in filenames (e.g., ToC index + page range) and/or maintain a mapping file.

### Section boundary / end-page computation may be incorrect for nested ToCs
- End page is derived from the **next ToC entry** regardless of level.
- Many PDFs interleave levels; a level-1 entry may be immediately followed by a level-2 entry starting on the same page.
  - Risk: unexpectedly short ranges, fragmented sections, or odd chunking.
  - Discussion: compute end pages based on the next ToC entry at the **same or higher** level.

### Text extraction flattens structure (hurts tables/code)
- The script concatenates spans with spaces and newlines, which can lose:
  - indentation (code blocks),
  - table alignment,
  - column/reading order,
  - figure captions positioned off-flow.
  - Discussion: prefer extraction modes that preserve ordering/blocks; consider per-page “block-based” extraction.

### Memory pressure from holding images in memory
- For large sections containing many embedded images/diagrams, keeping PIL images in `page_images` can create high RAM usage.
  - Discussion: cap images per section sent to the LLM, close images, or stream/thumbnail.

### Diagram detection is heuristic-sensitive
- Vector-graphics detection depends on `page.get_drawings()` and hard-coded thresholds.
  - Risk: document-dependent false positives/negatives (coordinate system varies).
  - Discussion: make thresholds configurable; add a diagnostic mode to inspect decisions.

### Index robustness (markdown escaping)
- Section titles are written directly into Markdown links; characters like `]` or `)` can break rendering.
  - Discussion: escape/normalize link text in `index.md`.

## Reliability / UX improvements (high value)

### Deterministic, unique naming strategy
- Proposed format: `NNN_pXXXX-YYYY_<slug>.md` (where NNN is ToC order, XXXX-YYYY is page range).
- Optionally emit a `manifest.json` (or `.csv`) to map:
  - section title → filename → page range → images referenced.

### Better ToC range computation
- Identify end page as the page before the next entry whose level is **<= current level**.
- Consider special-case “same page” entries to avoid zero-length or negative ranges.

### Improve raw extraction fidelity
- Investigate PyMuPDF extraction options to preserve:
  - block ordering,
  - monospaced spans,
  - line breaks and indentation.
- Consider storing raw per-page text with clear separators and metadata to help LLM.

### Control multimodal payload size
- Limit images passed to the vision model per section (or per page).
- Consider downscaling/thumbnailing images used only for context.

### Make output more “AI navigable”
- Standardize a short header in every output file:
  - section title, page range, source PDF name, and optionally ToC path.
- Consider writing a top-level `README` in `output_dir` describing how to navigate.

## Security / safety notes
- Add `.env` to `.gitignore` to avoid accidental key leakage.
- Consider explicitly documenting that content is sent to an external provider (Gemini) and costs apply.

## Code hygiene (minor)
- Remove unused imports (`sys`, `TimeoutError` appear unused).
- Consider light type hints and structured logging for long runs.

## “Easy wins” checklist (recommended first changes)
- Add `.env.example` (and update README if needed).
- Add `.gitignore` (ignore `.env`, output dirs, venv, etc.).
- Fix filename collisions via unique naming.
- Fix ToC end-page logic to respect levels.
- Escape titles in `index.md` output.

## Open questions for discussion
- Should a “section” strictly follow ToC hierarchy, or is “fixed token/page budget per file” acceptable?
- Do we want a hard cap on pages per section to control LLM request size/cost?
- Do we want provider abstraction now (multi-LLM support), or stabilize extraction quality first?

