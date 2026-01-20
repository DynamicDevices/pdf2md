import os
import re
import argparse
from dotenv import load_dotenv
from PIL import Image
import io
import sys
import time
import base64
import html
import threading
import random
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

# Load environment variables from .env file
load_dotenv()

class _MockGeminiResponse:
    def __init__(self, text):
        self.text = text


class _MockGeminiModel:
    def generate_content(self, _content):
        return _MockGeminiResponse("# Smoke Test\n\nOK (mock)\n")


class _MockAnthropicMessages:
    def create(self, **_kwargs):
        class _Resp:
            content = [type("Block", (), {"type": "text", "text": "# Smoke Test\n\nOK (mock)\n"})()]
        return _Resp()


class _MockAnthropicClient:
    def __init__(self):
        self.messages = _MockAnthropicMessages()


class RateLimiter:
    """
    Simple process-local, thread-safe rate limiter based on minimum interval.
    If rps <= 0, limiting is disabled.
    """

    def __init__(self, rps):
        self.rps = float(rps or 0)
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self):
        if self.rps <= 0:
            return

        interval = 1.0 / self.rps
        while True:
            with self._lock:
                now = time.monotonic()
                if now >= self._next_allowed:
                    self._next_allowed = now + interval
                    return
                sleep_for = self._next_allowed - now
            time.sleep(sleep_for)


def configure_llm_provider(llm_provider):
    """
    Configure and return (provider_ctx, model_vision, model_text, llm_model_name, llm_model_text_only).

    Set LLM_MOCK=1 to bypass real API calls (safe offline smoke tests).
    """
    llm_provider = (llm_provider or os.getenv("LLM_PROVIDER", "gemini")).strip().lower()
    llm_mock = os.getenv("LLM_MOCK", "").strip() in ("1", "true", "yes", "on")

    llm_rps = float(os.getenv("LLM_RPS", "0").strip() or "0")
    # Vision mode:
    # - auto: only send images when we detected/extracted them
    # - always: render and send page images for every processed page in a section
    # - never: text-only even if images exist
    provider_ctx = {
        "provider": llm_provider,
        "mock": llm_mock,
        "rate_limiter": RateLimiter(llm_rps),
    }

    # Retry/backoff tuning (shared across providers)
    # - Vision requests tend to be rate-limited more aggressively; allow more retries by default.
    provider_ctx["max_retries_text"] = int(os.getenv("LLM_MAX_RETRIES_TEXT", "5").strip() or "5")
    provider_ctx["max_retries_vision"] = int(os.getenv("LLM_MAX_RETRIES_VISION", "10").strip() or "10")
    provider_ctx["backoff_base_seconds"] = float(os.getenv("LLM_BACKOFF_BASE_SECONDS", "1").strip() or "1")
    provider_ctx["max_backoff_seconds"] = float(os.getenv("LLM_MAX_BACKOFF_SECONDS", "60").strip() or "60")
    provider_ctx["strict_mode"] = os.getenv("LLM_STRICT", "1").strip().lower() in ("1", "true", "yes", "on")

    if llm_provider == "anthropic":
        # Default to auto to avoid unnecessary vision costs; override with ANTHROPIC_VISION_MODE.
        provider_ctx["vision_mode"] = os.getenv("ANTHROPIC_VISION_MODE", "auto").strip().lower()
        provider_ctx["page_image_zoom"] = float(os.getenv("LLM_PAGE_IMAGE_ZOOM", "2.0").strip() or "2.0")
        anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        # Use a concrete, versioned model id by default. Some accounts/APIs do not support "-latest" aliases.
        # Newer Claude models exist; this default targets a recent Sonnet tier model.
        llm_model_name = os.getenv("ANTHROPIC_MODEL_NAME", "claude-sonnet-4-5-20250929")
        llm_model_text_only = os.getenv("ANTHROPIC_MODEL_TEXT_ONLY", llm_model_name)
        max_output_tokens = int(os.getenv("ANTHROPIC_MAX_OUTPUT_TOKENS", "8192"))

        if llm_mock:
            provider_ctx.update(
                {
                    "client": _MockAnthropicClient(),
                    "max_output_tokens": max_output_tokens,
                    "vision_model_name": llm_model_name,
                    "text_model_name": llm_model_text_only,
                }
            )
            return provider_ctx, llm_model_name, llm_model_text_only, llm_model_name, llm_model_text_only

        if not anthropic_api_key or anthropic_api_key.strip() == "" or anthropic_api_key == "your_api_key_here":
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")

        from anthropic import Anthropic
        client = Anthropic(api_key=anthropic_api_key)
        provider_ctx.update(
            {
                "api_key": anthropic_api_key,
                "client": client,
                "max_output_tokens": max_output_tokens,
                "vision_model_name": llm_model_name,
                "text_model_name": llm_model_text_only,
            }
        )
        return provider_ctx, llm_model_name, llm_model_text_only, llm_model_name, llm_model_text_only

    # Default: Gemini
    provider_ctx["vision_mode"] = os.getenv("LLM_VISION_MODE", "auto").strip().lower()
    provider_ctx["page_image_zoom"] = float(os.getenv("LLM_PAGE_IMAGE_ZOOM", "2.0").strip() or "2.0")
    google_api_key = os.getenv("GOOGLE_API_KEY")
    llm_model_name = os.getenv("LLM_MODEL_NAME", "gemini-2.5-flash")
    llm_model_text_only = os.getenv("LLM_MODEL_TEXT_ONLY", "gemini-2.5-flash")

    if llm_mock:
        provider_ctx.update({"vision_model_name": llm_model_name, "text_model_name": llm_model_text_only})
        return provider_ctx, _MockGeminiModel(), _MockGeminiModel(), llm_model_name, llm_model_text_only

    if not google_api_key or google_api_key == "your_api_key_here":
        raise RuntimeError("GOOGLE_API_KEY is not set.")

    # Lazy import so Anthropic-only users don't need the Gemini dependency.
    try:
        import google.generativeai as genai
    except ModuleNotFoundError as e:
        raise RuntimeError(
            "Gemini provider selected but google-generativeai is not installed. "
            "Install dependencies with: python -m pip install -r requirements.txt"
        ) from e
    genai.configure(api_key=google_api_key)
    model_vision = genai.GenerativeModel(llm_model_name)
    model_text = genai.GenerativeModel(llm_model_text_only)
    provider_ctx.update({"vision_model_name": llm_model_name, "text_model_name": llm_model_text_only})
    return provider_ctx, model_vision, model_text, llm_model_name, llm_model_text_only


def sanitize_filename(title):
    """
    Create a safe filename slug from a section title.

    NOTE: This does NOT guarantee uniqueness. Use make_section_filename() for section outputs.
    """
    # Remove problematic characters
    safe_name = re.sub(r'[\\/*?:"<>|]', "", str(title or ""))
    # Replace whitespace with underscores
    safe_name = re.sub(r"\s+", "_", safe_name.strip())
    safe_name = re.sub(r"_+", "_", safe_name).strip("_")
    # Remove anything that's likely to create weird paths / links
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "", safe_name)
    safe_name = safe_name.strip("._-").lower()
    return safe_name or "section"


def make_section_filename(title, toc_index, start_page):
    """
    Deterministically generate a unique per-section filename.

    We include ToC order + start page to avoid collisions from similar titles.
    """
    slug = sanitize_filename(title)[:100]
    return f"{int(toc_index):04d}_p{int(start_page):04d}_{slug}.md"


def escape_markdown_link_text(text):
    """
    Escape text for use inside markdown link text: [ ... ].
    """
    if text is None:
        return ""
    t = str(text).replace("\n", " ").strip()
    t = t.replace("\\", "\\\\")
    for ch in ("[", "]", "(", ")"):
        t = t.replace(ch, f"\\{ch}")
    return t


def parse_pages_spec(pages_spec):
    """
    Parse a page selection string like:
      "1-3,7,10-12" -> {0,1,2,6,9,10,11}  (0-indexed)

    Pages are specified as 1-indexed, inclusive ranges.
    """
    if pages_spec is None:
        return None
    s = str(pages_spec).strip()
    if not s:
        return None

    pages = set()
    parts = [p.strip() for p in s.split(",") if p.strip()]
    for part in parts:
        if "-" in part:
            a, b = part.split("-", 1)
            a = int(a.strip())
            b = int(b.strip())
            if a <= 0 or b <= 0:
                raise ValueError("Pages must be >= 1")
            lo = min(a, b)
            hi = max(a, b)
            for p in range(lo, hi + 1):
                pages.add(p - 1)
        else:
            p = int(part)
            if p <= 0:
                raise ValueError("Pages must be >= 1")
            pages.add(p - 1)
    return pages


def load_prompt_template(prompt_file="prompt.txt"):
    """Load the LLM prompt template from file."""
    try:
        with open(prompt_file, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"Warning: Prompt file '{prompt_file}' not found. Using default prompt.")
        return """You are a technical document conversion specialist. Convert the following raw text,
extracted from a PDF, into a clean, well-structured Markdown file.

- The main heading for this section is: '# {title}'
- Format all other text into paragraphs, subheadings (##, ###), and bullet points.
- Convert any text that looks like a table into a Markdown table.
- Format code snippets into Markdown code blocks (```).
- Preserve all technical details, register names, and values.
- For diagrams: Include image links AND text descriptions.
- Clean up PDF artifacts like broken line breaks, headers, or footers.
{image_references}

Raw Text:
---
{raw_content}
---
"""


def strip_markdown_fence(text):
    """Remove markdown code fences from LLM response if present."""
    text = text.strip()
    # Check if wrapped in ```markdown ... ```
    if text.startswith('```markdown') or text.startswith('```md'):
        lines = text.split('\n')
        # Remove first line (opening fence)
        lines = lines[1:]
        # Remove last line if it's a closing fence
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        text = '\n'.join(lines)
    # Also handle plain ``` fences
    elif text.startswith('```') and text.endswith('```'):
        text = text[3:-3].strip()
    return text


def _normalize_tech_token(tok):
    return re.sub(r"\s+", "", tok.strip().lower())


def _extract_tech_tokens(text):
    """
    Extract "technical" tokens that should not be hallucinated.
    We intentionally avoid catching plain list numbering.
    """
    if not text:
        return set()
    toks = set()

    # Hex literals
    for m in re.finditer(r"\b0x[0-9a-fA-F]+\b", text):
        toks.add(_normalize_tech_token(m.group(0)))

    # Bit ranges like [31:0] or 31:0
    for m in re.finditer(r"\[\s*\d{1,2}\s*:\s*\d{1,2}\s*\]", text):
        toks.add(_normalize_tech_token(m.group(0)))
    for m in re.finditer(r"\b\d{1,2}\s*:\s*\d{1,2}\b", text):
        toks.add(_normalize_tech_token(m.group(0)))

    # Numbers with units (common datasheet units)
    unit_re = r"(mV|V|uV|µV|A|mA|uA|µA|W|mW|uW|µW|Hz|kHz|MHz|GHz|MT/s|bps|kbps|Mbps|Gbps|ns|us|µs|ms|s|°C|C|%|dB)"
    for m in re.finditer(rf"\b[-+]?\d+(?:\.\d+)?\s*{unit_re}\b", text, flags=re.IGNORECASE):
        toks.add(_normalize_tech_token(m.group(0)))

    return toks


def decode_html_entities(text, max_passes=2):
    """
    Decode HTML entities that commonly appear from PDF extraction/LLM formatting.

    We do a couple of passes because strings like '&amp;#45;' need two unescapes:
      '&amp;#45;' -> '&#45;' -> '-'
    """
    if not text:
        return text
    s = str(text)
    for _ in range(max_passes):
        new = html.unescape(s)
        if new == s:
            break
        s = new
    return s


def _dedupe_table_images_around_verbatim_blocks(markdown_text):
    """
    Reduce noise by removing duplicate table image callouts/descriptions that the LLM may add
    outside verbatim table blocks.

    Strategy:
    - Identify table image paths referenced INSIDE VERBATIM_TABLE blocks.
    - Remove image lines like `![Table ...](./images/<that_table_image>)` that occur OUTSIDE verbatim blocks.
    - Also remove a short "Table X Description" paragraph immediately following such removed image lines.
    """
    if not markdown_text:
        return markdown_text

    lines = markdown_text.splitlines(True)  # keep newlines
    n = len(lines)

    # Mark verbatim block line ranges so we never touch them.
    in_verbatim = [False] * n
    i = 0
    while i < n:
        if "<!-- VERBATIM_TABLE_START -->" in lines[i]:
            j = i
            while j < n and "<!-- VERBATIM_TABLE_END -->" not in lines[j]:
                in_verbatim[j] = True
                j += 1
            if j < n:
                in_verbatim[j] = True
            i = j + 1
        else:
            i += 1

    # Collect table image paths that appear inside verbatim blocks.
    table_paths = set()
    img_re = re.compile(r"\(\./images/([^)]+)\)")
    for idx, line in enumerate(lines):
        if in_verbatim[idx]:
            for m in img_re.finditer(line):
                p = m.group(1)
                # Only target table crops
                if "_table_" in p:
                    table_paths.add(p)

    if not table_paths:
        return markdown_text

    def is_table_image_line(line, path):
        # Be conservative: only remove obvious "Table" image callouts.
        return (f"(./images/{path})" in line) and ("![Table" in line or "![Table " in line or "![Table(" in line)

    out = []
    skip_until = -1
    for idx in range(n):
        if idx <= skip_until:
            continue
        line = lines[idx]
        if in_verbatim[idx]:
            out.append(line)
            continue

        removed = False
        for p in table_paths:
            if is_table_image_line(line, p):
                removed = True
                # Also remove a short "description" chunk that often follows.
                j = idx + 1
                blank_skipped = 0
                while j < n and not in_verbatim[j]:
                    next_line = lines[j]
                    # stop at blank line or a heading/list start
                    if next_line.strip() == "":
                        # Allow a couple of blank lines between the image and the description.
                        blank_skipped += 1
                        if blank_skipped <= 2:
                            j += 1
                            continue
                        break
                    if next_line.lstrip().startswith("#") or next_line.lstrip().startswith(("* ", "- ", "1. ")):
                        break
                    # common patterns the LLM inserts
                    if "Table" in next_line or "Description" in next_line or next_line.strip().startswith("**"):
                        j += 1
                        continue
                    # If it's something else, stop (avoid deleting real content).
                    break
                skip_until = j - 1
                break

        if not removed:
            out.append(line)

    return "".join(out)


def _extract_verbatim_blocks(raw_text, start_marker="<!-- VERBATIM_TABLE_START -->", end_marker="<!-- VERBATIM_TABLE_END -->"):
    """
    Extract verbatim blocks from raw_text and replace them with stable placeholders.

    Returns:
      (cleaned_text, placeholder_to_block_dict, blocks_in_order)
    """
    if not raw_text:
        return raw_text, {}, []

    blocks = []
    placeholders = {}
    out_parts = []

    i = 0
    n = len(raw_text)
    while i < n:
        start = raw_text.find(start_marker, i)
        if start == -1:
            out_parts.append(raw_text[i:])
            break
        out_parts.append(raw_text[i:start])
        end = raw_text.find(end_marker, start)
        if end == -1:
            # Malformed marker pair; keep rest as-is.
            out_parts.append(raw_text[start:])
            break
        end = end + len(end_marker)
        block = raw_text[start:end]
        blocks.append(block)
        token = f"<<VERBATIM_TABLE_{len(blocks):02d}>>"
        placeholders[token] = block
        out_parts.append(token)
        i = end

    cleaned = "".join(out_parts)
    return cleaned, placeholders, blocks


def _restore_verbatim_blocks(formatted_markdown, placeholder_to_block, blocks_in_order):
    """
    Restore verbatim blocks into formatted markdown.

    If placeholders are missing (LLM removed them), append blocks at the end.
    """
    text = formatted_markdown or ""
    if not placeholder_to_block:
        return text

    missing_any = False
    for token, block in placeholder_to_block.items():
        if token in text:
            text = text.replace(token, block)
        else:
            missing_any = True

    if missing_any and blocks_in_order:
        text = text.rstrip() + "\n\n---\n\n## Verbatim tables\n\n" + "\n\n".join(blocks_in_order).rstrip() + "\n"

    return text


def _pil_image_to_anthropic_content_part(pil_image):
    """
    Convert a PIL image into an Anthropic Messages API "image" content part.

    Anthropic expects base64-encoded image bytes with an explicit media_type.
    """
    buf = io.BytesIO()
    # PNG is broadly supported and lossless; good default for diagrams.
    pil_image.save(buf, format="PNG")
    data_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": data_b64,
        },
    }


def _extract_anthropic_text(response):
    """Pull text blocks out of an Anthropic response object."""
    try:
        parts = []
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) == "text":
                parts.append(getattr(block, "text", ""))
        return "".join(parts)
    except Exception:
        # Best-effort fallback
        return str(response)


def call_llm_api(
    raw_content,
    title,
    provider_ctx,
    model,
    prompt_template,
    page_images=None,
    image_references=None,
    max_retries=None,
    strict_source_text=None,
):
    """
    Format raw extracted text into Markdown using the configured LLM provider.

    Supported providers:
      - Gemini (google-generativeai)
      - Anthropic (Claude via anthropic Messages API)

    Implements exponential backoff for rate limit errors (429/quota).

    Args:
        raw_content: Raw text extracted from PDF
        title: Section title
        provider_ctx: Dict describing provider configuration/context
        model: Provider-specific model handle (Gemini model object OR Anthropic model name string)
        prompt_template: Prompt template string
        page_images: Optional list of PIL Image objects for multimodal processing
        image_references: Optional list of image file paths for markdown links
        max_retries: Maximum number of retry attempts for rate limit errors
    """

    # Format image references for the prompt.
    # Avoid listing table crop images that are already embedded in raw_content (especially inside verbatim blocks),
    # which otherwise encourages the LLM to duplicate table callouts.
    image_refs_text = ""
    if image_references:
        filtered_refs = []
        for ref in image_references:
            try:
                # If the raw content already contains this reference, don't list it again.
                if ref and ref in raw_content:
                    continue
            except Exception:
                pass
            filtered_refs.append(ref)

        image_refs_text = "\n\nAvailable page images for this section:\n"
        for i, ref in enumerate(filtered_refs):
            image_refs_text += f"  - Image {i+1}: {ref}\n"

    llm_prompt = prompt_template.format(title=title, raw_content=raw_content, image_references=image_refs_text)
    provider = (provider_ctx or {}).get("provider", "gemini")
    # Normalize entity-escaped text for both strict-mode comparison and output readability.
    raw_content = decode_html_entities(raw_content)
    strict_source_text = decode_html_entities(raw_content if strict_source_text is None else strict_source_text)

    is_vision = bool(page_images)
    if max_retries is None:
        if is_vision:
            max_retries = int((provider_ctx or {}).get("max_retries_vision", 10))
        else:
            max_retries = int((provider_ctx or {}).get("max_retries_text", 5))
    max_backoff_seconds = float((provider_ctx or {}).get("max_backoff_seconds", 60) or 60)
    backoff_base_seconds = float((provider_ctx or {}).get("backoff_base_seconds", 1) or 1)

    def _retry_after_seconds(err):
        """
        Best-effort extraction of Retry-After from provider exceptions, if exposed.
        Returns float seconds or None.
        """
        try:
            resp = getattr(err, "response", None)
            if resp is None:
                return None
            headers = getattr(resp, "headers", None)
            if not headers:
                return None
            ra = headers.get("retry-after") or headers.get("Retry-After")
            if not ra:
                return None
            return float(ra)
        except Exception:
            return None

    strict_mode = bool((provider_ctx or {}).get("strict_mode", False))

    # Retry loop with exponential backoff (+ jitter)
    for attempt in range(max_retries):
        try:
            if attempt == 0:
                print(f"  ({provider}) Sending to format: {title}", flush=True)
            else:
                print(f"  ({provider}) Retry {attempt}/{max_retries-1} for: {title}", flush=True)

            if provider == "anthropic":
                # Lazy import so Gemini-only users don't need anthropic installed.
                try:
                    from anthropic import Anthropic
                except Exception as imp_err:
                    raise RuntimeError(
                        "Anthropic provider selected but the 'anthropic' package is not installed. "
                        "Install it via requirements.txt."
                    ) from imp_err

                client = provider_ctx.get("client")
                if client is None:
                    api_key = provider_ctx.get("api_key")
                    client = Anthropic(api_key=api_key)

                content = [{"type": "text", "text": llm_prompt}]
                if page_images:
                    for img in page_images:
                        content.append(_pil_image_to_anthropic_content_part(img))

                max_tokens = int(provider_ctx.get("max_output_tokens", 8192))
                rate_limiter = (provider_ctx or {}).get("rate_limiter")
                if rate_limiter:
                    rate_limiter.wait()

                response = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": content}],
                )

                result_text = _extract_anthropic_text(response)
                result = decode_html_entities(strip_markdown_fence(result_text))

                if strict_mode:
                    src = _extract_tech_tokens(strict_source_text)
                    out = _extract_tech_tokens(result)
                    new_tokens = sorted(out - src)
                    if new_tokens:
                        print(
                            f"  STRICT_MODE: rejecting LLM output for '{title}' due to new technical tokens: "
                            f"{', '.join(new_tokens[:10])}{' ...' if len(new_tokens) > 10 else ''}",
                            flush=True,
                        )
                        footer_pattern = re.compile(r"\n--- End of Page \d+ ---\n")
                        safe_raw = re.sub(footer_pattern, "\n\n", raw_content)
                        token_list = ", ".join(new_tokens[:12]) + (" ..." if len(new_tokens) > 12 else "")
                        return (
                            f"# {title}\n\n"
                            f"[STRICT_MODE: LLM output rejected due to potential hallucinated technical values]\n\n"
                            f"New technical tokens detected: {token_list}\n\n"
                            f"{safe_raw}"
                        )

                return result

            # Default: Gemini
            # If we have page images, send them along with the text for better diagram understanding
            rate_limiter = (provider_ctx or {}).get("rate_limiter")
            if rate_limiter:
                rate_limiter.wait()

            if page_images:
                content_parts = [llm_prompt]
                content_parts.extend(page_images)
                response = model.generate_content(content_parts)
            else:
                response = model.generate_content(llm_prompt)

            # Strip markdown code fences if present
            result = decode_html_entities(strip_markdown_fence(response.text))
            if strict_mode:
                src = _extract_tech_tokens(strict_source_text)
                out = _extract_tech_tokens(result)
                new_tokens = sorted(out - src)
                if new_tokens:
                    print(
                        f"  STRICT_MODE: rejecting LLM output for '{title}' due to new technical tokens: "
                        f"{', '.join(new_tokens[:10])}{' ...' if len(new_tokens) > 10 else ''}",
                        flush=True,
                    )
                    footer_pattern = re.compile(r"\n--- End of Page \d+ ---\n")
                    safe_raw = re.sub(footer_pattern, "\n\n", raw_content)
                    token_list = ", ".join(new_tokens[:12]) + (" ..." if len(new_tokens) > 12 else "")
                    return (
                        f"# {title}\n\n"
                        f"[STRICT_MODE: LLM output rejected due to potential hallucinated technical values]\n\n"
                        f"New technical tokens detected: {token_list}\n\n"
                        f"{safe_raw}"
                    )
            return result

        except Exception as e:
            error_str = str(e)

            # Anthropic model-not-found is commonly a 404 with "model: <name>".
            if provider == "anthropic" and ("not_found_error" in error_str or "model:" in error_str):
                print(
                    "  Hint: Anthropic returned a model-not-found error. "
                    "Set ANTHROPIC_MODEL_NAME (and optionally ANTHROPIC_MODEL_TEXT_ONLY) in your .env "
                    "to a valid model id for your account.",
                    flush=True,
                )

            # Check if this is a rate limit / overload error (provider-specific)
            # Anthropic commonly returns 429 and may include type strings like rate_limit_error/overloaded_error.
            is_rate_limited = (
                "429" in error_str
                or "529" in error_str
                or "rate_limit" in error_str.lower()
                or "overloaded" in error_str.lower()
                or "resource exhausted" in error_str.lower()
                or "quota" in error_str.lower()
            )

            if is_rate_limited:
                if attempt < max_retries - 1:
                    # Exponential backoff with full jitter (AWS-style), capped:
                    #   sleep = random(0, min(cap, base * 2^attempt))
                    cap = min(max_backoff_seconds, backoff_base_seconds * (2 ** attempt))
                    wait_time = random.uniform(0, cap) if cap > 0 else 0.0

                    # If provider supplies Retry-After, respect it (at least that long).
                    ra = _retry_after_seconds(e)
                    if ra is not None:
                        wait_time = max(wait_time, ra)

                    print(
                        f"  ⏳ Rate limit/overload hit for '{title}', waiting {wait_time:.1f}s before retry...",
                        flush=True,
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"  ERROR: Rate limit exceeded after {max_retries} retries for '{title}'", flush=True)
            else:
                # Non-rate-limit error, don't retry
                print(f"  ERROR: LLM API call failed for '{title}': {e}", flush=True)

            # Fallback to simple formatting on error
            fallback_content = f"# {title}\n\n[LLM_API_ERROR: {e}]\n\n"

            # Clean up page markers
            footer_pattern = re.compile(r"\n--- End of Page \d+ ---\n")
            fallback_content += re.sub(footer_pattern, "\n\n", raw_content)

            return fallback_content

    # Should never reach here, but just in case
    return f"# {title}\n\n[ERROR: Max retries exceeded]\n\n{raw_content}"


def is_real_diagram(page, drawings):
    """
    Determine if a page contains real technical diagrams vs just tables/headers/footers.

    Uses smart heuristics based on:
    - Page coverage percentage
    - Size of largest drawing element
    - Ratio of small vs large drawings

    Args:
        page: PyMuPDF page object
        drawings: List of drawing objects from page.get_drawings()

    Returns:
        (bool, str): (should_save_image, reason_for_decision)
    """
    if not drawings:
        return False, "no drawings found"

    # Get page dimensions
    rect = page.rect
    page_area = rect.width * rect.height

    if page_area == 0:
        return False, "invalid page area"

    # Analyze drawings
    total_drawing_area = 0
    drawing_sizes = []
    small_drawing_count = 0

    for drawing in drawings:
        if 'rect' in drawing:
            r = drawing['rect']
            width = r[2] - r[0]
            height = r[3] - r[1]
            area = width * height

            total_drawing_area += area
            drawing_sizes.append(area)

            # Count small drawings (likely table borders, lines)
            if area < 100:
                small_drawing_count += 1

    # Calculate metrics
    coverage_percent = (total_drawing_area / page_area) * 100
    largest_drawing = max(drawing_sizes) if drawing_sizes else 0
    small_ratio = (small_drawing_count / len(drawings)) * 100 if drawings else 0

    # Decision logic
    # Real diagrams typically have:
    # - High page coverage (>20%) OR large elements (>50k sq units)
    # - Not mostly tiny elements (<80% small)

    if coverage_percent > 20:
        return True, f"high coverage ({coverage_percent:.1f}%)"

    if largest_drawing > 50000:
        return True, f"large element ({largest_drawing:.0f} sq units)"

    if coverage_percent > 10 and small_ratio < 80:
        return True, f"moderate coverage ({coverage_percent:.1f}%) with substantial elements"

    # Likely just tables, headers, or formatting
    return False, f"low coverage ({coverage_percent:.1f}%), small elements ({small_ratio:.0f}% tiny)"


def is_real_diagram_v2(page, drawings, page_text=None):
    """
    Improved diagram detection for auto-vision decisions.

    Adds an additional signal: if the page contains a figure heading/caption and has
    non-trivial vector drawings, treat it as a diagram even if the basic heuristics
    would classify it as a table/formatting.
    """
    is_diagram, reason = is_real_diagram(page, drawings)
    if is_diagram:
        return True, reason

    # Fallback: look for figure captions/headings.
    try:
        rect = page.rect
        page_area = rect.width * rect.height
        if page_area <= 0:
            return False, reason

        total_drawing_area = 0.0
        drawing_sizes = []
        for d in drawings or []:
            r = d.get("rect")
            if not r:
                continue
            width = r[2] - r[0]
            height = r[3] - r[1]
            area = float(width * height)
            total_drawing_area += area
            drawing_sizes.append(area)

        coverage_percent = (total_drawing_area / page_area) * 100.0 if page_area else 0.0
        largest = max(drawing_sizes) if drawing_sizes else 0.0

        txt = (page_text or "").lower()
        has_figure_cue = ("figure" in txt) or ("block diagram" in txt) or ("schematic" in txt)

        # If the page calls out a figure and there's meaningful vector content, treat as diagram.
        if has_figure_cue and (coverage_percent > 5.0 or largest > 20000.0):
            return True, f"figure cue + vector content (coverage {coverage_percent:.1f}%, largest {largest:.0f})"
    except Exception:
        pass

    return False, reason


def _rect_intersection_area(a, b):
    inter = a & b
    if inter.is_empty:
        return 0.0
    return float(inter.get_area())


def _extract_page_text_with_tables(page, img_dir, page_num, y_min=None, y_max=None, zoom=2.0):
    """
    Extract page text while preferring structured table extraction.

    - Extract tables via page.find_tables(), render cropped table images, and insert verbatim markdown tables.
    - Skip text blocks that overlap table regions to avoid duplicated / garbled table text.
    - Apply optional y_min/y_max clipping (PDF coordinate space) for same-page section splits.

    Returns:
      (page_text, table_image_refs)
    """
    # Local import because fitz is lazily imported in the main conversion function.
    import fitz  # PyMuPDF

    table_entries = []
    table_image_refs = []

    # Find tables (best-effort: API available in PyMuPDF >= 1.23+)
    try:
        tf = page.find_tables()
        tables = list(getattr(tf, "tables", []) or [])
    except Exception:
        tables = []

    for ti, t in enumerate(tables):
        try:
            bbox = getattr(t, "bbox", None)
            if not bbox:
                continue
            rect = fitz.Rect(bbox)
            # Respect y clipping
            if y_min is not None and rect.y1 < y_min:
                continue
            if y_max is not None and rect.y0 >= y_max:
                continue

            md = t.to_markdown()
            if not md.strip():
                continue

            # Render a cropped image of the table for verification
            img_filename = f"page_{page_num + 1}_table_{ti+1}.png"
            img_path = os.path.join(img_dir, img_filename)
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, clip=rect)
            with open(img_path, "wb") as f:
                f.write(pix.tobytes("png"))

            table_image_refs.append(f"./images/{img_filename}")
            table_entries.append(
                {
                    "y0": float(rect.y0),
                    "rect": rect,
                    "md": md,
                    "img_ref": f"./images/{img_filename}",
                }
            )
        except Exception:
            continue

    table_entries.sort(key=lambda x: x["y0"])

    # Pull blocks and interleave tables by y-position.
    blocks = page.get_text("blocks")  # tuples: x0,y0,x1,y1,text,block_no,block_type
    out_parts = []
    next_table_idx = 0

    def emit_tables_up_to(y):
        nonlocal next_table_idx
        while next_table_idx < len(table_entries) and table_entries[next_table_idx]["y0"] <= y:
            te = table_entries[next_table_idx]
            out_parts.append("\n<!-- VERBATIM_TABLE_START -->\n")
            out_parts.append(f"![Table (page {page_num + 1})]({te['img_ref']})\n\n")
            out_parts.append(te["md"].rstrip() + "\n")
            out_parts.append("<!-- VERBATIM_TABLE_END -->\n\n")
            next_table_idx += 1

    for b in blocks:
        x0, by0, x1, by1, text = float(b[0]), float(b[1]), float(b[2]), float(b[3]), b[4]

        # Apply y clipping
        if y_min is not None and by1 < y_min:
            continue
        if y_max is not None and by0 >= y_max:
            continue

        # Emit any tables that begin before this block
        emit_tables_up_to(by0)

        # Skip blocks that overlap tables (avoid duplicated table text)
        block_rect = fitz.Rect(x0, by0, x1, by1)
        skip = False
        for te in table_entries:
            inter_area = _rect_intersection_area(block_rect, te["rect"])
            if inter_area > 0:
                # Skip if a meaningful portion overlaps
                if inter_area / max(1.0, float(block_rect.get_area())) > 0.2:
                    skip = True
                    break
        if skip:
            continue

        out_parts.append(text)

    # Emit remaining tables at end of page
    emit_tables_up_to(1e18)

    return "".join(out_parts), table_image_refs


def convert_pdf_to_markdown(pdf_path, output_dir, prompt_file="prompt.txt", max_workers=4, llm_provider=None, force=False, pages=None):
    """
    Main function to convert the PDF to a structured set of Markdown files.

    Args:
        pdf_path: Path to the input PDF file
        output_dir: Directory to save the markdown files
        prompt_file: Path to the LLM prompt template file
        max_workers: Maximum number of parallel LLM API calls (default: 4)
    """

    # --- 0. Configure LLM Provider ---
    try:
        provider_ctx, model_vision, model_text, llm_model_name, llm_model_text_only = configure_llm_provider(llm_provider)
    except Exception as e:
        print(f"Error: {e}")
        print("Please create a .env file with your API key (see .env.example)")
        return

    if provider_ctx.get("provider") == "anthropic":
        print("LLM provider: Anthropic (Claude)")
        print(f"Vision model (with images): {llm_model_name}")
        print(f"Text-only model (no images): {llm_model_text_only}")
    else:
        print("LLM provider: Gemini")
        print(f"Vision model (with images): {llm_model_name}")
        print(f"Text-only model (no images): {llm_model_text_only}")

    # Load the prompt template
    prompt_template = load_prompt_template(prompt_file)

    # --- 1. Setup Directories ---
    if not os.path.exists(pdf_path):
        print(f"Error: PDF file not found at '{pdf_path}'")
        return

    # Lazy import so --smoke-test and Anthropic-only usage doesn't require PyMuPDF at import time.
    try:
        import fitz  # PyMuPDF
    except ModuleNotFoundError as e:
        if str(e).strip() in ("No module named 'fitz'", 'No module named "fitz"'):
            print("Error: Missing dependency PyMuPDF (module 'fitz').")
            print("Install dependencies, then re-run:")
            print("  python -m pip install -r requirements.txt")
            print()
            print("Or install PyMuPDF directly:")
            print("  python -m pip install PyMuPDF")
            return
        raise

    # Validate output_dir early to avoid wasting LLM calls.
    if output_dir.lower().endswith((".md", ".markdown")):
        print(f"Error: Output path looks like a file, but --output must be a directory: '{output_dir}'")
        print("Use a directory name instead, for example:")
        print("  -o output_markdown")
        print("  -o IMX93RM_out")
        return

    if os.path.exists(output_dir) and not os.path.isdir(output_dir):
        print(f"Error: Output path exists but is not a directory: '{output_dir}'")
        print("Please choose an output directory path (or delete/rename the existing file).")
        return

    img_dir = os.path.join(output_dir, "images")
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(img_dir, exist_ok=True)
    print(f"Output will be saved to '{output_dir}'")
    
    doc = fitz.open(pdf_path)
    selected_pages = parse_pages_spec(pages) if pages is not None else None
    if selected_pages is not None:
        # Clamp to document bounds
        selected_pages = {p for p in selected_pages if 0 <= p < doc.page_count}
        if not selected_pages:
            print("No selected pages remain after clamping to document page count. Nothing to do.", flush=True)
            doc.close()
            return
    
    # --- 2. Get Table of Contents (ToC) ---
    # Use simple=False so we can access destination coordinates for same-page section splits.
    toc = doc.get_toc(simple=False)
    if not toc:
        print("Error: Could not extract Table of Contents. Aborting.")
        print("This script relies on a ToC to logically chunk the file.")
        return

    print(f"Found {len(toc)} sections in the Table of Contents.")

    # --- 3. Extract Content from All Sections (Sequential) ---
    print("\nPhase 1: Extracting content from sections...")

    # Track which pages have been processed to reduce duplication across ToC entries.
    # Note: some ToC entries start on the same page. For quality, we still include each
    # section's own start page even if it overlaps with a previous section.
    processed_pages = set()

    # Collect all sections to process
    sections_to_process = []

    # Track sections for index.md (includes metadata for TOC structure)
    sections_for_index = []

    def _toc_entry_parts(entry):
        """
        PyMuPDF ToC entries are typically:
          - simple=True: [level, title, page]
          - simple=False: [level, title, page, dest_dict]
        """
        level = entry[0]
        title = entry[1]
        start_page = entry[2]
        dest = entry[3] if len(entry) > 3 and isinstance(entry[3], dict) else {}
        start_y = 0.0
        try:
            to = dest.get("to")
            start_y = float(getattr(to, "y", 0.0)) if to is not None else 0.0
        except Exception:
            start_y = 0.0
        return level, title, start_page, start_y

    for i, entry in enumerate(toc):
        level, title, start_page, start_y = _toc_entry_parts(entry)

        # Page numbers in PyMuPDF ToC are 1-indexed, pages are 0-indexed
        start_page_idx = start_page - 1

        # Determine end page based on the next entry at the same or higher level.
        # This avoids using child entries as boundaries.
        end_page_idx = doc.page_count - 1
        end_y = None
        for j in range(i + 1, len(toc)):
            next_level, _next_title, next_start_page, next_start_y = _toc_entry_parts(toc[j])
            if next_level <= level:
                next_start_page_idx = next_start_page - 1
                if next_start_page_idx == start_page_idx:
                    end_page_idx = start_page_idx
                    end_y = next_start_y
                else:
                    end_page_idx = next_start_page_idx - 1
                break

        # Ensure start/end pages are valid (for single-page sections)
        if start_page_idx > end_page_idx:
            end_page_idx = start_page_idx

        # Decide which pages to process for this section.
        # - Prefer not to duplicate pages across sections.
        # - Always include the section's own start page to avoid losing content when
        #   multiple sections start on the same page.
        pages_in_section = set(range(start_page_idx, end_page_idx + 1))
        if selected_pages is not None:
            pages_in_section = pages_in_section & selected_pages
        # Always include the section's start page *only if it is within selected pages*.
        start_included = {start_page_idx} if (selected_pages is None or start_page_idx in selected_pages) else set()
        pages_to_process = sorted((pages_in_section - processed_pages) | start_included)

        if not pages_to_process:
            print(f"  Skipping: '{title}' (Pages {start_page_idx + 1} to {end_page_idx + 1}) - already processed")
            continue

        start_page_idx = pages_to_process[0]
        end_page_idx = pages_to_process[-1]

        print(f"  Extracting: '{title}' (Pages {start_page_idx + 1} to {end_page_idx + 1})")

        section_raw_content = ""
        section_filename = make_section_filename(title, toc_index=i + 1, start_page=start_page)
        image_references = []  # Track image filenames for markdown links
        vision_page_nums = set()
        # Map page_num -> {"y_min": float|None, "y_max": float|None} in PDF coordinate space
        # Used to crop page images for vision models to avoid leaking adjacent sections on shared pages.
        vision_page_clips = {}

        vision_mode = (provider_ctx.get("vision_mode") or "auto").lower()
        if vision_mode not in ("auto", "always", "never"):
            vision_mode = "auto"

        # 4a. Iterate through selected pages in this section (may be non-contiguous)
        for page_num in pages_to_process:
            try:
                page = doc.load_page(page_num)
            except Exception as e:
                print(f"  Warning: Could not load page {page_num + 1}. Skipping. Error: {e}")
                continue

            # Text extraction with clipping on shared pages (use ToC destination y coords),
            # plus table-first extraction.
            y_min = start_y if page_num == start_page_idx else None
            y_max = end_y if (end_y is not None and page_num == end_page_idx) else None
            try:
                page_text, table_refs = _extract_page_text_with_tables(
                    page,
                    img_dir=img_dir,
                    page_num=page_num,
                    y_min=y_min,
                    y_max=y_max,
                    zoom=float(provider_ctx.get("page_image_zoom") or 2.0),
                )
                section_raw_content += page_text
                if not section_raw_content.endswith("\n"):
                    section_raw_content += "\n"
                image_references.extend(table_refs)
            except Exception:
                # Fallback: full-page text (no table-first, no clipping)
                section_raw_content += page.get_text("text")
                if not section_raw_content.endswith("\n"):
                    section_raw_content += "\n"

            blocks = page.get_text("dict")["blocks"]

            # Check for and extract embedded images (bitmaps)
            #
            # NOTE: In some PDFs, PyMuPDF returns image blocks (type==1) that do NOT
            # include an "xref" key (e.g. inline images). Previously we assumed xref
            # always exists and emitted noisy warnings like: KeyError: 'xref'.
            embedded_images_found = False
            inline_img_count = 0
            skipped_img_blocks = 0
            for block in blocks:
                if block.get("type") != 1:
                    continue

                try:
                    img_xref = block.get("xref", 0) or 0
                    if img_xref:
                        img = doc.extract_image(img_xref)
                        img_bytes = img.get("image") or b""
                        img_ext = img.get("ext") or "png"
                        if not img_bytes:
                            skipped_img_blocks += 1
                            continue

                        img_filename = f"page_{page_num + 1}_img_{img_xref}.{img_ext}"
                    else:
                        # Inline image blocks: save the bytes directly if present.
                        img_bytes = block.get("image") or b""
                        img_ext = block.get("ext") or "png"
                        if not img_bytes:
                            skipped_img_blocks += 1
                            continue

                        inline_img_count += 1
                        img_filename = f"page_{page_num + 1}_img_inline_{inline_img_count}.{img_ext}"

                    img_path = os.path.join(img_dir, img_filename)
                    with open(img_path, "wb") as img_file:
                        img_file.write(img_bytes)

                    image_references.append(f"./images/{img_filename}")
                    embedded_images_found = True
                    print(f"    Extracted embedded image: {img_filename}")

                except Exception:
                    # Avoid spamming logs for PDFs that have many tiny inline images.
                    skipped_img_blocks += 1

            if skipped_img_blocks:
                print(
                    f"  Warning: Skipped {skipped_img_blocks} embedded image block(s) on page {page_num + 1} (missing data or unsupported format)"
                )

            # Check if page has real diagrams (not just tables/headers)
            # Use smart heuristics to filter false positives
            should_save_diagram = False
            try:
                # Get the page's drawing commands to see if there are vector graphics
                drawings = page.get_drawings()
                if drawings and len(drawings) > 0:
                    # Use improved diagram detection for auto vision decisions.
                    is_diagram, reason = is_real_diagram_v2(page, drawings, page_text=page.get_text("text"))
                    if is_diagram:
                        should_save_diagram = True
                        print(f"    ✓ Page {page_num + 1}: Diagram detected - {reason}")
                    else:
                        print(f"    ✗ Page {page_num + 1}: Skipping - {reason}")
            except Exception as e:
                print(f"  Warning: Error analyzing drawings on page {page_num + 1}: {e}")

            # Only render full page if there are real diagrams that couldn't be extracted
            if should_save_diagram and not embedded_images_found:
                try:
                    # Render at 2x resolution for better quality (150 DPI)
                    zoom = 2.0
                    mat = fitz.Matrix(zoom, zoom)
                    pix = page.get_pixmap(matrix=mat)
                    img_data = pix.tobytes("png")
                    img_filename = f"page_{page_num + 1}_diagram.png"
                    img_path = os.path.join(img_dir, img_filename)
                    with open(img_path, "wb") as f:
                        f.write(img_data)

                    image_references.append(f"./images/{img_filename}")
                    print(f"    Rendered full page diagram: {img_filename}")

                except Exception as e:
                    print(f"  Warning: Could not render page {page_num + 1} as image: {e}")

            # Decide whether to use vision for this page.
            use_vision_for_page = False
            if vision_mode == "always":
                use_vision_for_page = True
            elif vision_mode == "auto":
                if embedded_images_found or should_save_diagram:
                    use_vision_for_page = True

            if use_vision_for_page:
                vision_page_nums.add(page_num)
                if y_min is not None or y_max is not None:
                    vision_page_clips[int(page_num)] = {
                        "y_min": float(y_min) if y_min is not None else None,
                        "y_max": float(y_max) if y_max is not None else None,
                    }

            section_raw_content += f"\n--- End of Page {page_num + 1} ---\n"

        # 4c. Check if section has content and collect for processing
        if not section_raw_content.strip():
             print(f"  Skipping '{title}' - no content extracted.")
             continue

        # Check if output file already exists (for resume capability)
        section_md_path = os.path.join(output_dir, section_filename)
        file_exists = os.path.exists(section_md_path)

        # Track for index.md (preserve TOC structure) - do this regardless of whether we process
        sections_for_index.append({
            'level': level,
            'title': title,
            'page': start_page,
            'filename': section_filename
        })

        # Decode common HTML entity escapes from extraction (e.g. &amp;#45; -> -).
        section_raw_content = decode_html_entities(section_raw_content)

        # Extract verbatim table blocks and replace with placeholders for the LLM prompt.
        # We will restore the exact blocks back into the final Markdown output after the LLM runs.
        raw_for_prompt, verbatim_placeholders, verbatim_blocks = _extract_verbatim_blocks(section_raw_content)

        # If file already exists, skip LLM processing but keep in index (unless forced)
        if file_exists and not force:
            print(f"  ✓ Resuming: '{title}' already exists, skipping LLM processing")
        else:
            if file_exists and force:
                print(f"  ↻ Forcing regenerate: '{title}' (overwriting existing output)", flush=True)
            # Select model: use vision model if we plan to send images, otherwise use text-only model
            if vision_mode != "never" and len(vision_page_nums) > 0:
                selected_model = model_vision
                model_info = f"vision ({llm_model_name}, {len(vision_page_nums)} page image(s))"
            else:
                selected_model = model_text
                model_info = f"text-only ({llm_model_text_only})"

            # Collect section data for parallel processing
            sections_to_process.append({
                'title': title,
                'filename': section_filename,
                'raw_content': raw_for_prompt,
                'strict_source_text': section_raw_content,
                'verbatim_placeholders': verbatim_placeholders,
                'verbatim_blocks': verbatim_blocks,
                'image_references': image_references,
                'model': selected_model,
                'model_info': model_info,
                'provider_ctx': provider_ctx,
                'pdf_path': pdf_path,
                'vision_page_nums': sorted(list(vision_page_nums)),
                'vision_page_clips': vision_page_clips,
            })

        # Mark these pages as processed
        processed_pages.update(pages_to_process)

    doc.close()

    # Show resume statistics
    total_sections = len(sections_for_index)
    new_sections = len(sections_to_process)
    resumed_sections = total_sections - new_sections

    print(f"\nPhase 1 Complete:")
    print(f"  Total sections: {total_sections}")
    print(f"  New sections to process: {new_sections}")
    if resumed_sections > 0:
        print(f"  Resumed (already exist): {resumed_sections}")
    print()

    # --- 5. Format All Sections with LLM (Parallel) ---
    if new_sections == 0:
        print("\nPhase 2: All sections already exist, skipping LLM processing.\n")
    else:
        print(f"\nPhase 2: Formatting {new_sections} new sections with LLM (max {max_workers} parallel workers)...")
        print("(Files will be written as they complete)\n")

    def format_and_write_section(section_data):
        """Format a single section using the LLM API and write it immediately."""
        try:
            title = section_data['title']
            filename = section_data['filename']
            model_info = section_data['model_info']

            print(f"  → Formatting '{title}' using {model_info}", flush=True)

            # Build page images just-in-time for vision-capable requests.
            page_images = None
            vision_pages = section_data.get("vision_page_nums") or []
            vision_clips = section_data.get("vision_page_clips") or {}
            if vision_pages:
                try:
                    import fitz  # PyMuPDF
                    zoom = float(section_data.get("provider_ctx", {}).get("page_image_zoom") or 2.0)
                    mat = fitz.Matrix(zoom, zoom)
                    page_images = []
                    doc_local = fitz.open(section_data["pdf_path"])
                    try:
                        for p in vision_pages:
                            page = doc_local.load_page(int(p))
                            pix = page.get_pixmap(matrix=mat)
                            img_data = pix.tobytes("png")
                            im = Image.open(io.BytesIO(img_data))

                            # Crop the image to the section range on shared pages to avoid bleeding
                            # into adjacent sections (especially in always-vision mode).
                            clip = vision_clips.get(int(p)) or {}
                            y_min = clip.get("y_min")
                            y_max = clip.get("y_max")
                            if y_min is not None or y_max is not None:
                                w, h = im.size
                                top = int(max(0, round(float(y_min) * zoom))) if y_min is not None else 0
                                bottom = int(min(h, round(float(y_max) * zoom))) if y_max is not None else h
                                # Add a tiny padding to avoid cutting through text baselines.
                                pad = int(max(0, round(4 * zoom)))
                                top = max(0, top - pad)
                                bottom = min(h, bottom + pad)
                                if bottom > top:
                                    im = im.crop((0, top, w, bottom))

                            page_images.append(im)
                    finally:
                        doc_local.close()
                except Exception as img_err:
                    print(f"  Warning: Could not render vision page images for '{title}': {img_err}", flush=True)
                    page_images = None

            formatted_markdown = call_llm_api(
                section_data['raw_content'],
                section_data['title'],
                section_data['provider_ctx'],
                section_data['model'],
                prompt_template,
                page_images,
                section_data['image_references'],
                strict_source_text=section_data.get("strict_source_text"),
            )

            # Restore verbatim tables into the final output (do not trust the LLM to keep them).
            formatted_markdown = _restore_verbatim_blocks(
                formatted_markdown,
                section_data.get("verbatim_placeholders") or {},
                section_data.get("verbatim_blocks") or [],
            )
            # Remove common duplicated table callouts outside verbatim blocks.
            formatted_markdown = _dedupe_table_images_around_verbatim_blocks(formatted_markdown)

            # Close any in-memory images we created.
            if page_images:
                for im in page_images:
                    try:
                        im.close()
                    except Exception:
                        pass

            # Write immediately after formatting (defensive: ensure output dir exists).
            os.makedirs(output_dir, exist_ok=True)
            section_md_path = os.path.join(output_dir, filename)
            with open(section_md_path, "w", encoding="utf-8") as f:
                f.write(formatted_markdown)

            print(f"  ✓ Completed and wrote '{title}' -> {filename}", flush=True)
            return (filename, True)

        except Exception as e:
            print(f"  ✗ Error formatting '{section_data['title']}': {e}", flush=True)
            # Write error fallback
            try:
                os.makedirs(output_dir, exist_ok=True)
                section_md_path = os.path.join(output_dir, section_data['filename'])
                with open(section_md_path, "w", encoding="utf-8") as f:
                    f.write(f"# {section_data['title']}\n\n[ERROR: {e}]\n\n{section_data['raw_content']}")
                return (section_data['filename'], False)
            except Exception as write_err:
                print(f"  ✗ Could not write error file: {write_err}", flush=True)
                return (section_data['filename'], False)

    # Process all sections in parallel, writing as they complete
    completed_count = 0
    error_count = 0
    total_sections_to_process = len(sections_to_process)

    if total_sections_to_process > 0:

        print(f"Starting parallel processing of {total_sections_to_process} sections...", flush=True)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_section = {executor.submit(format_and_write_section, section): section for section in sections_to_process}

            for future in as_completed(future_to_section):
                try:
                    filename, success = future.result()
                    completed_count += 1
                    if not success:
                        error_count += 1

                    # Show progress
                    percent = (completed_count / total_sections_to_process) * 100
                    print(f"\n  Progress: {completed_count}/{total_sections_to_process} sections ({percent:.1f}%)", flush=True)

                except Exception as e:
                    completed_count += 1
                    error_count += 1
                    print(f"  ✗ Unexpected error processing section: {e}", flush=True)

        print("\nAll sections processed, closing thread pool...", flush=True)

    # --- 6. Create Master Index ---
    print("Creating index.md with links to all created sections...", flush=True)

    index_md_path = os.path.join(output_dir, "index.md")
    with open(index_md_path, "w", encoding="utf-8") as f:
        f.write("# Technical Reference Manual - Index\n\n")
        f.write("This document provides a top-level index for the converted technical manual.\n\n")

        for section in sections_for_index:
            level = section['level']
            title = section['title']
            page = section['page']
            filename = section['filename']
            indent = "  " * (level - 1)
            safe_title = escape_markdown_link_text(title)
            f.write(f"{indent}* [{safe_title} (Page {page})](./{filename})\n")

    print(f"Index created with {len(sections_for_index)} sections.", flush=True)

    # Summary
    print("\n" + "=" * 60, flush=True)
    print("Conversion Complete!", flush=True)
    print("=" * 60, flush=True)
    print(f"Sections processed:  {completed_count}/{total_sections_to_process}", flush=True)
    if error_count > 0:
        print(f"Errors encountered:  {error_count}", flush=True)
    print(f"Output directory:    {output_dir}", flush=True)
    print(f"Start with:          {index_md_path}", flush=True)
    print("=" * 60, flush=True)


def main():
    """Parse command line arguments and run the conversion."""
    parser = argparse.ArgumentParser(
        description="Convert large technical PDF files to structured Markdown with images.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s -i manual.pdf -o output_md
  %(prog)s --pdf manual.pdf --output output_md --prompt custom_prompt.txt

Configuration:
  Create a .env file with either:
    - Gemini: GOOGLE_API_KEY (and optional LLM_MODEL_NAME / LLM_MODEL_TEXT_ONLY)
    - Anthropic: ANTHROPIC_API_KEY (and optional ANTHROPIC_MODEL_NAME / ANTHROPIC_MODEL_TEXT_ONLY)
  Select provider with LLM_PROVIDER=gemini|anthropic or --provider
  See .env.example for template
        """
    )

    parser.add_argument(
        "-i", "--pdf",
        dest="pdf_path",
        default=os.getenv("PDF_PATH", "cc1312r7.pdf"),
        help="Path to input PDF file (default: from .env or 'cc1312r7.pdf')"
    )

    parser.add_argument(
        "-o", "--output",
        dest="output_dir",
        default=os.getenv("OUTPUT_DIR", "output_markdown"),
        help="Output directory for markdown files (default: from .env or 'output_markdown')"
    )

    parser.add_argument(
        "-p", "--prompt",
        dest="prompt_file",
        default="prompt.txt",
        help="Path to LLM prompt template file (default: 'prompt.txt')"
    )

    parser.add_argument(
        "-w", "--workers",
        dest="max_workers",
        type=int,
        default=4,
        help="Maximum number of parallel LLM API calls (default: 4)"
    )

    parser.add_argument(
        "--provider",
        dest="llm_provider",
        choices=["gemini", "anthropic"],
        default=os.getenv("LLM_PROVIDER", "gemini"),
        help="LLM provider to use (default: from LLM_PROVIDER env var or 'gemini')",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess and overwrite existing section markdown files (disable resume behavior for this run).",
    )
    parser.add_argument(
        "--pages",
        default=os.getenv("PDF_PAGES", "").strip() or None,
        help='Only process content intersecting these PDF pages (1-indexed). Example: --pages "9,11-13".',
    )

    parser.add_argument(
        "--llm-rps",
        dest="llm_rps",
        type=float,
        default=None,
        help="Throttle LLM requests to at most this many requests per second (shared across workers). "
             "Can also be set via LLM_RPS env var. 0 disables throttling.",
    )

    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Call the configured LLM once with a tiny prompt and exit (no PDF needed). Set LLM_MOCK=1 to run offline.",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("PDF to Markdown Converter")
    print("=" * 60)
    print(f"Input PDF:      {args.pdf_path}")
    print(f"Output Dir:     {args.output_dir}")
    print(f"Prompt:         {args.prompt_file}")
    print(f"Max Workers:    {args.max_workers}")
    print(f"LLM Provider:   {args.llm_provider}")
    if args.llm_rps is not None:
        print(f"LLM RPS:        {args.llm_rps}")
    print("=" * 60)
    print()

    if args.smoke_test:
        prompt_template = load_prompt_template(args.prompt_file)
        try:
            if args.llm_rps is not None:
                os.environ["LLM_RPS"] = str(args.llm_rps)
            provider_ctx, model_vision, _model_text, llm_model_name, _llm_model_text_only = configure_llm_provider(args.llm_provider)
            # Print resolved model info for debugging (no secrets).
            print(f"Resolved model (vision):     {provider_ctx.get('vision_model_name', llm_model_name)}")
            print(f"Resolved model (text-only):  {provider_ctx.get('text_model_name', _llm_model_text_only)}")
            output = call_llm_api(
                raw_content="Smoke test: reply with 'OK'.",
                title="Smoke Test",
                provider_ctx=provider_ctx,
                model=model_vision,
                prompt_template=prompt_template,
                page_images=None,
                image_references=None,
            )
            print("\n" + "=" * 60)
            print("SMOKE TEST OUTPUT:")
            print("=" * 60)
            print(output)
            return
        except Exception as e:
            print(f"Smoke test failed: {e}", file=sys.stderr)
            sys.exit(1)

    if args.llm_rps is not None:
        os.environ["LLM_RPS"] = str(args.llm_rps)
    convert_pdf_to_markdown(
        args.pdf_path,
        args.output_dir,
        args.prompt_file,
        args.max_workers,
        args.llm_provider,
        args.force,
        pages=args.pages,
    )


if __name__ == "__main__":
    main()