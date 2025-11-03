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
- Uses Google's Gemini API to format and clean up extracted text
- Converts tables, code blocks, and technical content to proper Markdown
- Creates a master index file for easy navigation
- Configurable via environment variables and command-line arguments
- Customizable LLM prompt template

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

4. Set up your API key:
```bash
cp .env.example .env
# Edit .env and add your Google API key
```

Get your API key from [Google AI Studio](https://aistudio.google.com/)

## Configuration

### Environment Variables (.env)

Create a `.env` file based on `.env.example`:

```bash
# Google API Configuration
GOOGLE_API_KEY=your_api_key_here

# Model to use (gemini-1.5-flash is fast/cheap, gemini-1.5-pro is slower/better)
LLM_MODEL_NAME=gemini-1.5-flash

# Default paths (optional, can override via command line)
PDF_PATH=cc1312r7.pdf
OUTPUT_DIR=output_markdown
```

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

### Specify Input and Output

```bash
python pdf2md.py -i /path/to/manual.pdf -o output_directory
```

### Use Custom Prompt Template

```bash
python pdf2md.py -i manual.pdf -o output_md -p custom_prompt.txt
```

### Command Line Options

```
usage: pdf2md.py [-h] [-i PDF_PATH] [-o OUTPUT_DIR] [-p PROMPT_FILE]

Convert large technical PDF files to structured Markdown with images.

optional arguments:
  -h, --help            show this help message and exit
  -i PDF_PATH, --pdf PDF_PATH
                        Path to input PDF file (default: from .env or 'cc1312r7.pdf')
  -o OUTPUT_DIR, --output OUTPUT_DIR
                        Output directory for markdown files (default: from .env or 'output_markdown')
  -p PROMPT_FILE, --prompt PROMPT_FILE
                        Path to LLM prompt template file (default: 'prompt.txt')
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
2. **Process Each Section**: For each ToC entry:
   - Extracts text and images from the relevant page range
   - Saves images to the `images/` directory
   - Inserts image placeholders in the text
3. **Format with LLM**: Sends the raw extracted text to Gemini API to:
   - Clean up PDF artifacts (page breaks, headers, footers)
   - Format as proper Markdown (headings, lists, tables, code blocks)
   - Convert image placeholders to Markdown image syntax
4. **Save Output**: Creates individual markdown files for each section plus a master index

## Requirements

- Python 3.7+
- PyMuPDF (fitz) - PDF processing
- google-generativeai - Gemini API access
- python-dotenv - Environment variable management

## Cost Considerations

The tool uses Google's Gemini API, which charges based on tokens processed:
- **gemini-1.5-flash**: Fast and cost-effective (~$0.075 per 1M input tokens)
- **gemini-1.5-pro**: More capable but slower/expensive (~$1.25 per 1M input tokens)

For a 2100-page technical manual, expect to process several million tokens. Monitor your usage at [Google AI Studio](https://aistudio.google.com/).

## Troubleshooting

### "Error: GOOGLE_API_KEY is not set"
- Make sure you created a `.env` file with your API key
- Check that the key is valid at [Google AI Studio](https://aistudio.google.com/)

### "Error: Could not extract Table of Contents"
- The tool requires a PDF with a proper ToC/bookmarks structure
- Check if your PDF has a ToC by opening it in a PDF reader
- Consider manually splitting PDFs without ToC structure

### LLM API rate limits
- The script includes a 1-second delay between API calls
- For rate limit errors, consider adding longer delays in `call_llm_api()`
- Use `gemini-1.5-flash` for faster processing with lower rate limits

### Images not extracting
- Some PDFs have embedded images that are difficult to extract
- Check the `images/` folder to verify what was extracted
- Vector graphics may not extract properly (PyMuPDF limitation)

## License

This tool is provided as-is for technical document conversion purposes.

## Notes

- This is a one-time conversion tool, not designed for batch processing
- Quality is prioritized over performance
- The output is optimized for AI agent consumption, not human reading
- Large PDFs may take considerable time to process due to API rate limits
