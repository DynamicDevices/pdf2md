#!/usr/bin/env python3
"""
Refresh datasheet output README.md files with generated run metadata (no LLM calls).

This is useful when:
- You already ran a conversion, but the output README files still contain old template
  placeholders like "Conversion metadata (fill this in)" / "Record:".
- You want idempotent metadata blocks (rewritten each run) instead of endlessly appending.

The script will:
- Remove placeholder "Conversion metadata..." sections and legacy "Record:" blocks
- Remove any previous generated metadata block between:
    <!-- RUN_METADATA_START --> ... <!-- RUN_METADATA_END -->
- Ensure a "## Notes" section exists
- Append a fresh generated metadata block (if provided)
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True).strip()


def _maybe(cmd: list[str]) -> str:
    try:
        return _run(cmd)
    except Exception:
        return ""


def rewrite_readme(path: Path, title: str, run_metadata_block: str, extra_note: str = "") -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""

    # Strip legacy placeholder sections that tell users to "fill this in".
    text = re.sub(r"(?ms)^\s*##\s+Conversion metadata.*?(?=^\s*##\s+|\Z)", "", text)
    text = re.sub(r"(?ms)^\s*Record:\s*\n(?:-.*\n)+", "", text)

    # Strip any previous generated metadata block (idempotent updates).
    text = re.sub(
        r"(?ms)^\s*<!--\s*RUN_METADATA_START\s*-->.*?<!--\s*RUN_METADATA_END\s*-->\s*",
        "",
        text,
    )

    # Strip legacy appended run-metadata blocks that were not wrapped in markers.
    # These typically look like:
    # ---
    # ## Run metadata (generated)
    # - Date: ...
    # ...
    #
    # Remove ALL of them so the README doesn't accumulate duplicates.
    text = re.sub(
        r"(?ms)^\s*---\s*\n##\s+Run metadata\s+\(generated\)\s*\n.*?(?=^\s*(?:---\s*\n##\s+Run metadata\s+\(generated\)\s*\n|##\s+Notes\b|<!--\s*RUN_METADATA_START\s*-->|\Z))",
        "",
        text,
    )
    # Also handle legacy blocks that start directly with "## Run metadata (generated)" (no leading '---').
    text = re.sub(
        r"(?ms)^\s*##\s+Run metadata\s+\(generated\)\s*\n.*?(?=^\s*(?:##\s+Run metadata\s+\(generated\)\s*\n|##\s+Notes\b|<!--\s*RUN_METADATA_START\s*-->|\Z))",
        "",
        text,
    )

    text = text.strip() + ("\n" if text.strip() else "")

    if not text.startswith("#"):
        text = f"# {title}\n\n" + text

    if "## Notes" not in text:
        text = text.rstrip() + "\n\n## Notes\n"
        if extra_note:
            text += f"\n- {extra_note}\n"
        else:
            text += "\n- \n"
    else:
        if extra_note and extra_note not in text:
            text = re.sub(r"(?m)^(##\s+Notes\s*)$", r"\1\n- " + extra_note, text, count=1)

    run_metadata_block = (run_metadata_block or "").strip()
    if run_metadata_block:
        text = (
            text.rstrip()
            + "\n\n<!-- RUN_METADATA_START -->\n"
            + run_metadata_block
            + "\n<!-- RUN_METADATA_END -->\n"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh datasheets output README.md files with generated metadata")
    ap.add_argument("--doc-dir", required=True, help="Path to datasheets doc dir (e.g. datasheets/manufacturers/nxp/AN13917)")
    ap.add_argument("--provider", default=os.environ.get("LLM_PROVIDER") or "anthropic", help="anthropic|gemini")
    ap.add_argument("--workers", type=int, default=int(os.environ.get("WORKERS") or 2))
    ap.add_argument("--llm-rps", default=os.environ.get("LLM_RPS") or "0.5")
    ap.add_argument("--pdf2md-repo", default="DynamicDevices/pdf2md")
    args = ap.parse_args()

    doc_dir = Path(args.doc_dir).resolve()
    out_text = doc_dir / "outputs" / "pdftotext"
    out_auto = doc_dir / "outputs" / "pdf2md" / "auto"
    out_always = doc_dir / "outputs" / "pdf2md" / "always"

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    repo_dir = Path(__file__).resolve().parents[1]
    pdf2md_sha = _maybe(["git", "-C", str(repo_dir), "rev-parse", "HEAD"])
    dirty_count = _maybe(["bash", "-lc", f"cd {repo_dir} && git status --porcelain | wc -l | tr -d ' '"])

    pdftotext_ver = _maybe(["bash", "-lc", "pdftotext -v 2>&1 | head -n 1"])

    if args.provider == "anthropic":
        model_info = f"ANTHROPIC_MODEL_NAME={os.environ.get('ANTHROPIC_MODEL_NAME','')} / ANTHROPIC_MODEL_TEXT_ONLY={os.environ.get('ANTHROPIC_MODEL_TEXT_ONLY','')}"
    else:
        model_info = f"LLM_MODEL_NAME={os.environ.get('LLM_MODEL_NAME','')} / LLM_MODEL_TEXT_ONLY={os.environ.get('LLM_MODEL_TEXT_ONLY','')}"

    # Source PDF path: prefer an actual file in source/
    source_pdf = ""
    src_dir = doc_dir / "source"
    if src_dir.exists():
        pdfs = sorted(src_dir.glob("*.pdf"))
        if pdfs:
            source_pdf = str(pdfs[0])

    # pdftotext
    if out_text.exists():
        txt_meta = "\n".join(
            [
                "---",
                "## Run metadata (generated)",
                f"- Date: {now}",
                (f"- Source: {source_pdf}" if source_pdf else "- Source:"),
                (f"- pdftotext: {pdftotext_ver}" if pdftotext_ver else "- pdftotext:"),
                (
                    f"- Command: pdftotext -layout \"{source_pdf}\" \"{out_text / 'output.txt'}\""
                    if source_pdf
                    else "- Command:"
                ),
            ]
        )
        rewrite_readme(out_text / "README.md", "pdftotext baseline", txt_meta, "Record any post-processing you applied (if any).")

    # pdf2md auto
    if out_auto.exists():
        cmd_auto = ""
        if source_pdf:
            cmd_auto = f'python pdf2md.py -i "{source_pdf}" -o "{out_auto}" -p prompt.txt -w {args.workers} --provider {args.provider} (with vision=auto)'
        auto_meta = "\n".join(
            [
                "---",
                "## Run metadata (generated)",
                f"- Date: {now}",
                (f"- Source: {source_pdf}" if source_pdf else "- Source:"),
                f"- pdf2md repo: `{args.pdf2md_repo}`",
                (f"- pdf2md commit: {pdf2md_sha}" if pdf2md_sha else "- pdf2md commit:"),
                (f"- pdf2md dirty files: {dirty_count}" if dirty_count else "- pdf2md dirty files:"),
                f"- Provider: {args.provider}",
                f"- Models: {model_info}",
                "- Vision mode: auto",
                f"- LLM_RPS: {args.llm_rps}",
                f"- Workers: {args.workers}",
                (f"- Command: {cmd_auto}" if cmd_auto else "- Command:"),
            ]
        )
        rewrite_readme(out_auto / "README.md", "pdf2md – auto mode", auto_meta, "")

    # pdf2md always (if exists)
    if out_always.exists():
        cmd_always = ""
        if source_pdf:
            cmd_always = f'python pdf2md.py -i "{source_pdf}" -o "{out_always}" -p prompt.txt -w {args.workers} --provider {args.provider} (with vision=always)'
        always_meta = "\n".join(
            [
                "---",
                "## Run metadata (generated)",
                f"- Date: {now}",
                (f"- Source: {source_pdf}" if source_pdf else "- Source:"),
                f"- pdf2md repo: `{args.pdf2md_repo}`",
                (f"- pdf2md commit: {pdf2md_sha}" if pdf2md_sha else "- pdf2md commit:"),
                (f"- pdf2md dirty files: {dirty_count}" if dirty_count else "- pdf2md dirty files:"),
                f"- Provider: {args.provider}",
                f"- Models: {model_info}",
                "- Vision mode: always",
                f"- LLM_RPS: {args.llm_rps}",
                f"- Workers: {args.workers}",
                (f"- Command: {cmd_always}" if cmd_always else "- Command:"),
            ]
        )
        rewrite_readme(out_always / "README.md", "pdf2md – always-vision mode", always_meta, "")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

