# PDF to Multi-page Markdown Converter

A tool for converting large technical reference PDFs (2100+ pages) into well-structured, AI-friendly Markdown files with extracted images.

## Purpose

This tool allows very large technical reference PDF files to be useful to AI coding agents by:
- Breaking down large PDFs into reasonably sized markdown files
- Extracting and organizing images (block diagrams, schematics, etc.)
- Using LLM assistance to clean up PDF artifacts and structure the content
- Creating a navigable index for easy access

This is a one-time conversion tool that favors quality over performance. The output is designed to be directly accessible by AI agents without requiring RAG (Retrieval-Augmented Generation).

## Features

- Extracts PDF Table of Contents to intelligently chunk the document
- Preserves all images and diagrams from the PDF
- Uses an LLM (Gemini by default; optional Anthropic Claude support) to format and clean up extracted text
- Converts tables, code blocks, and technical content to proper Markdown
- Creates a master index file for easy navigation
- Configurable via environment variables and command-line arguments
- Customizable LLM prompt template
- **Parallel processing** with configurable worker count for faster conversions
- **Resume capability** - automatically skips already-processed sections
- **Smart diagram detection** - filters out false positives (tables, headers) from real diagrams
- **Dual model support** - uses vision model for pages with diagrams, text-only model otherwise
- **Exponential backoff** for API rate limit handling

## Installation

1. Clone or download this repository

2. Create and activate a virtual environment:
```bash
# Create virtual environment
python3 -m venv venv

# Activate it
# On macOS/Linux:
source venv/bin/activate

# On Windows:
# venv\Scripts\activate
```

3. Install Python dependencies:
```bash
pip install -r requirements.txt
```

4. Set up your API key(s):
```bash
cp .env.example .env
# Edit .env and add your API key(s)
```

Get API keys from:
- Gemini: [Google AI Studio](https://aistudio.google.com/)
- Anthropic: Anthropic Console

## Configuration

### Environment Variables (.env)

Create a `.env` file based on `.env.example`:

```bash
# LLM Provider Selection
# - gemini (default): uses GOOGLE_API_KEY + Gemini models
# - anthropic: uses ANTHROPIC_API_KEY + Claude models
LLM_PROVIDER=gemini

# Optional: throttle LLM request rate (shared across worker threads)
# 0 disables throttling.
LLM_RPS=0

# Optional: retry/backoff tuning
# Vision requests often hit stricter limits; defaults are higher for vision.
LLM_MAX_RETRIES_TEXT=5
LLM_MAX_RETRIES_VISION=10
LLM_BACKOFF_BASE_SECONDS=1
LLM_MAX_BACKOFF_SECONDS=60

# Optional: strict mode to reduce hallucinations (recommended for datasheets)
# When enabled, the tool will reject LLM outputs that introduce new "technical tokens"
# (e.g., hex values, bit ranges, numeric values with units) that were not present in the extracted source text.
LLM_STRICT=1

# Optional: render resolution multiplier for page images sent to vision models
# (higher = sharper but slower/more tokens). 2.0 is a good default.
LLM_PAGE_IMAGE_ZOOM=2.0

# Google API Configuration
GOOGLE_API_KEY=your_api_key_here

# Vision behavior for Gemini:
# - auto: only send images when we detected/extracted diagrams/images
# - always: render and send page images for every processed page in a section
# - never: never send images (text-only)
LLM_VISION_MODE=auto

# Vision model - used for pages with diagrams/images (multimodal)
LLM_MODEL_NAME=gemini-2.5-flash

# Text-only model - used for pages without images (faster/cheaper)
LLM_MODEL_TEXT_ONLY=gemini-2.5-flash

# Anthropic (Claude) Configuration (only used when LLM_PROVIDER=anthropic)
ANTHROPIC_API_KEY=your_api_key_here

# Vision behavior for Anthropic:
# - always: render and send page images for every processed page in a section (best quality; higher cost)
# - auto: only send images when we detected/extracted diagrams/images
# - never: never send images (text-only)
ANTHROPIC_VISION_MODE=auto

# Vision model - used for pages with diagrams/images (multimodal)
ANTHROPIC_MODEL_NAME=claude-sonnet-4-5-20250929

# Text-only model - used for pages without images (faster/cheaper)
ANTHROPIC_MODEL_TEXT_ONLY=claude-sonnet-4-5-20250929

# Max output tokens per request (Claude)
ANTHROPIC_MAX_OUTPUT_TOKENS=8192

# Default paths (optional, can override via command line)
PDF_PATH=cc1312r7.pdf
OUTPUT_DIR=output_markdown
```

The tool automatically selects the appropriate model based on whether a page contains diagrams or images. You can use different models for each purpose (e.g., a more capable model for vision tasks).

### Anthropic quick start

1. Set in `.env`:
   - `LLM_PROVIDER=anthropic`
   - `ANTHROPIC_API_KEY=...`
   - Optionally override `ANTHROPIC_MODEL_NAME` / `ANTHROPIC_MODEL_TEXT_ONLY`

2. Smoke test (fast, no PDF required):
```bash
python pdf2md.py --smoke-test --provider anthropic
```

Or use the helper script (loads `.env` automatically):
```bash
./scripts/smoke_test_anthropic.sh
```

3. Convert a real PDF (recommended helper):
```bash
./scripts/convert_pdf_anthropic.sh -i /path/to/manual.pdf -o outputs/manual
```

Notes:
- `-o/--output` must be a **directory**, not a `.md` filename.
- We recommend writing outputs under `outputs/` (git-ignored) so you can keep results locally without committing them.
- For big PDFs, start conservative: `-w 2 --llm-rps 0.5` and increase gradually.
- If you want Claude to use vision even on pages without extracted diagrams, set `ANTHROPIC_VISION_MODE=always` (higher cost).
- For datasheets / register maps where correctness is critical, set `LLM_STRICT=1`.

### Prompt Template (prompt.txt)

The LLM prompt used for formatting is stored in `prompt.txt`. You can customize this file to adjust how the LLM processes your content. The template uses Python string formatting with `{title}` and `{raw_content}` placeholders.

## Usage

**Note**: Make sure your virtual environment is activated before running:
```bash
source venv/bin/activate  # macOS/Linux
# or venv\Scripts\activate on Windows
```

### Basic Usage

Convert a PDF using default settings:
```bash
python pdf2md.py
```

### Use Anthropic Claude (instead of Gemini)

Via environment variable:
```bash
LLM_PROVIDER=anthropic python pdf2md.py -i manual.pdf -o output_md
```

Via command-line:
```bash
python pdf2md.py -i manual.pdf -o output_md --provider anthropic
```

### Use Gemini (Google)
Via environment variable:
```bash
LLM_PROVIDER=gemini python pdf2md.py -i manual.pdf -o output_md
```

Via command-line:
```bash
python pdf2md.py -i manual.pdf -o output_md --provider gemini
```

### Specify Input and Output

```bash
python pdf2md.py -i /path/to/manual.pdf -o output_directory
```

### Force re-generation (overwrite existing output)

By default, the tool will **resume** and skip sections that already have output files. To re-run after changing prompts/settings/code:

```bash
python pdf2md.py -i manual.pdf -o output_md --force
```

### Process only specific pages (cheaper iteration)

When iterating on extraction quality, you can limit work to specific PDF pages (1-indexed):

```bash
python pdf2md.py -i manual.pdf -o output_md --pages "9,11-13"
```

This will only process sections that intersect those pages (and will only extract/send those pages to the LLM).

### Datasheets workflow (recommended for repeatable validation)

This repo can optionally use a `datasheets` submodule to store **public** source PDFs and their conversion outputs in a consistent structure.

- **Critical**: do **not** store confidential / NDA / proprietary PDFs in `datasheets/`.

Convert a datasheet into the `datasheets/` structure:

```bash
./scripts/datasheets_convert.sh \
  --manufacturer nxp \
  --doc-id AN13917 \
  --pdf "/path/to/AN13917.pdf" \
  --provider anthropic \
  --workers 2 \
  --llm-rps 0.5
```

#### Page-slice iteration without touching `datasheets/` (PAGE TEST MODE)

If you pass `--pages` through to `pdf2md.py`, `scripts/datasheets_convert.sh` automatically switches to **PAGE TEST MODE**:

- Outputs go under `outputs/page_tests/...` (git-ignored)
- The `datasheets/` submodule is **not** modified

Example:

```bash
./scripts/datasheets_convert.sh \
  --manufacturer nxp \
  --doc-id AN13917 \
  --pdf "/path/to/AN13917.pdf" \
  --provider anthropic \
  --workers 2 \
  --llm-rps 0.5 \
  --force \
  -- --pages "8-12"
```

### Use Custom Prompt Template

```bash
python pdf2md.py -i manual.pdf -o output_md -p custom_prompt.txt
```

### Parallel Processing with More Workers

```bash
# Use 8 parallel workers for faster processing
python pdf2md.py -i manual.pdf -o output_md -w 8
```

### Throttle LLM request rate (avoid provider rate limits)

```bash
# Cap to ~1 request/second total (shared across workers)
python pdf2md.py -i manual.pdf -o output_md --provider anthropic --llm-rps 1
```

### Command Line Options

```
usage: pdf2md.py [-h] [-i PDF_PATH] [-o OUTPUT_DIR] [-p PROMPT_FILE] [-w MAX_WORKERS]

Convert large technical PDF files to structured Markdown with images.

optional arguments:
  -h, --help            show this help message and exit
  -i PDF_PATH, --pdf PDF_PATH
                        Path to input PDF file (default: from .env or 'cc1312r7.pdf')
  -o OUTPUT_DIR, --output OUTPUT_DIR
                        Output directory for markdown files (default: from .env or 'output_markdown')
  -p PROMPT_FILE, --prompt PROMPT_FILE
                        Path to LLM prompt template file (default: 'prompt.txt')
  -w MAX_WORKERS, --workers MAX_WORKERS
                        Maximum number of parallel LLM API calls (default: 4)
```

## Output Structure

The tool creates the following structure:

```
output_markdown/
├── index.md                      # Master index with links to all sections
├── images/                       # All extracted images
│   ├── p23_xref456.png
│   ├── p45_xref789.jpg
│   └── ...
├── section_1.md                  # Individual section files
├── section_2.md
└── ...
```

- `index.md`: Start here - contains links to all sections organized by the PDF's Table of Contents
- `images/`: All extracted images, named by page number and reference ID
- Section files: One markdown file per ToC section, with proper headings, tables, code blocks, and image references

## How It Works

1. **Extract Table of Contents**: Uses PyMuPDF to read the PDF's ToC structure
2. **Process Each Section** (Phase 1 - Sequential): For each ToC entry:
   - Extracts text and images from the relevant page range
   - Detects diagrams using smart heuristics (page coverage, element sizes)
   - Saves embedded images and renders full-page diagrams when appropriate
   - Skips already-processed sections (resume capability)
3. **Format with LLM** (Phase 2 - Parallel): Using configurable worker threads:
   - Selects vision model for pages with images, text-only model otherwise
   - Cleans up PDF artifacts (page breaks, headers, footers)
   - Formats as proper Markdown (headings, lists, tables, code blocks)
   - Writes output files immediately as each section completes
   - Implements exponential backoff for rate limit handling
4. **Save Output**: Creates individual markdown files for each section plus a master index

## Requirements

- Python 3.7+
- PyMuPDF (fitz) - PDF processing
- google-generativeai - Gemini API access
- anthropic - Anthropic Claude API access
- python-dotenv - Environment variable management
- Pillow (PIL) - Image processing for multimodal API

## Cost Considerations

The tool uses Google's Gemini API, which charges based on tokens processed:
- **gemini-2.5-flash**: Fast and cost-effective (default)
- **gemini-2.5-pro**: More capable but slower/expensive

Check current pricing at [Google AI Studio](https://aistudio.google.com/).

For a 2100-page technical manual, expect to process several million tokens. The dual-model approach helps reduce costs by using text-only processing for pages without diagrams.

## Troubleshooting
### "Error code: 404 ... not_found_error ... model: ..."
- Your Anthropic model name is not valid for your account/API.
- Set `ANTHROPIC_MODEL_NAME` (and optionally `ANTHROPIC_MODEL_TEXT_ONLY`) to a valid model id.

### "Error: Missing dependency PyMuPDF (module 'fitz')"
- Install deps in your active environment:
```bash
python -m pip install -r requirements.txt
```

### Pip fails inside conda `(base)` with `Invalid version: '4.0.0-unsupported'`
- This is usually caused by a broken installed package metadata in that environment (often `pyodbc`).
- Recommended: use a clean venv:
```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install -U pip setuptools wheel packaging
python -m pip install -r requirements.txt
```


### "Error: GOOGLE_API_KEY is not set"
- Make sure you created a `.env` file with your API key
- Check that the key is valid at [Google AI Studio](https://aistudio.google.com/)

### "Error: Could not extract Table of Contents"
- The tool requires a PDF with a proper ToC/bookmarks structure
- Check if your PDF has a ToC by opening it in a PDF reader
- If the PDF has no bookmarks/ToC, re-run with `--no-toc` to process the whole PDF (or your selected `--pages`) as a single section

### LLM API rate limits
- The script implements automatic exponential backoff (1s, 2s, 4s, 8s, 16s delays)
- Rate limit errors (429) are automatically retried up to 5 times
- Reduce `--workers` if you consistently hit rate limits
- Use `gemini-2.5-flash` for higher rate limits

### Images not extracting
- Some PDFs have embedded images that are difficult to extract
- Check the `images/` folder to verify what was extracted
- Vector graphics are rendered as full-page images when detected as real diagrams

### Resuming interrupted conversions
- The tool automatically detects existing output files and skips re-processing them
- Simply re-run the same command to resume from where you left off
- Delete specific `.md` files if you want to regenerate them

## Planned Improvements

### Multi-Provider LLM Support

Currently the tool only supports Google's Gemini API. Future versions will add support for:

- **OpenAI** (GPT-4o, GPT-4o-mini) - Vision and text models
- **Anthropic Claude** (Claude Sonnet, Claude Haiku) - Vision and text models
- **Local LLMs** (Ollama, llama.cpp) - For offline/private processing

**Implementation Strategy:**

1. **Provider Abstraction Layer** - Create a base `LLMProvider` class with common interface methods (`generate_content()`, `supports_vision()`, `get_model_info()`)

2. **Provider Implementations** - Each provider gets its own class:
   - `GeminiProvider` (current implementation, refactored)
   - `OpenAIProvider` (using `openai` package)
   - `ClaudeProvider` (using `anthropic` package)
   - `OllamaProvider` (using `ollama` package or REST API)

3. **Configuration** - Select provider via environment variable or CLI flag:
   ```bash
   # Via environment
   LLM_PROVIDER=openai
   OPENAI_API_KEY=sk-...

   # Via command line
   python pdf2md.py -i manual.pdf --provider claude
   ```

4. **Graceful Fallback** - Vision models used when available; automatic fallback to text-only for providers/models without vision support

## License

This tool is provided as-is for technical document conversion purposes.

## Notes

- This is a one-time conversion tool designed for large technical reference documents
- Quality is prioritized over performance, but parallel processing speeds up conversions
- The output is optimized for AI agent consumption, not human reading
- Large PDFs benefit from the parallel workers feature (`-w` flag)
- The resume capability makes it safe to interrupt and restart long conversions
