import fitz  # PyMuPDF
import os
import re
import google.generativeai as genai
import argparse
from dotenv import load_dotenv
from PIL import Image
import io
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

# Load environment variables from .env file
load_dotenv()


def sanitize_filename(title):
    """Creates a safe, simple filename from a section title."""
    # Remove problematic characters
    safe_name = re.sub(r'[\\/*?:"<>|]', "", title)
    # Replace spaces with underscores
    safe_name = re.sub(r"\s+", "_", safe_name)
    # Basic truncation to avoid overly long filenames
    return safe_name.lower()[:75] + ".md"


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


def call_llm_api(raw_content, title, model, prompt_template, page_images=None, image_references=None, max_retries=5):
    """
    Uses the Google Generative AI (Gemini) API to format raw text into markdown.
    Implements exponential backoff for rate limit errors (429).

    Args:
        raw_content: Raw text extracted from PDF
        title: Section title
        model: Gemini model instance
        prompt_template: Prompt template string
        page_images: Optional list of PIL Image objects for multimodal processing
        image_references: Optional list of image file paths for markdown links
        max_retries: Maximum number of retry attempts for rate limit errors
    """

    # Format image references for the prompt
    image_refs_text = ""
    if image_references:
        image_refs_text = "\n\nAvailable page images for this section:\n"
        for i, ref in enumerate(image_references):
            image_refs_text += f"  - Image {i+1}: {ref}\n"

    llm_prompt = prompt_template.format(title=title, raw_content=raw_content, image_references=image_refs_text)

    # Retry loop with exponential backoff
    for attempt in range(max_retries):
        try:
            if attempt == 0:
                print(f"  (Gemini API) Sending to format: {title}", flush=True)
            else:
                print(f"  (Gemini API) Retry {attempt}/{max_retries-1} for: {title}", flush=True)

            # If we have page images, send them along with the text for better diagram understanding
            if page_images:
                content_parts = [llm_prompt]
                content_parts.extend(page_images)
                response = model.generate_content(content_parts)
            else:
                response = model.generate_content(llm_prompt)

            # Strip markdown code fences if present
            result = strip_markdown_fence(response.text)
            return result

        except Exception as e:
            error_str = str(e)

            # Check if this is a rate limit error (429)
            if "429" in error_str or "Resource Exhausted" in error_str or "quota" in error_str.lower():
                if attempt < max_retries - 1:
                    # Exponential backoff: 2^attempt seconds (1s, 2s, 4s, 8s, 16s)
                    wait_time = 2 ** attempt
                    print(f"  ⏳ Rate limit hit for '{title}', waiting {wait_time}s before retry...", flush=True)
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


def convert_pdf_to_markdown(pdf_path, output_dir, prompt_file="prompt.txt", max_workers=4):
    """
    Main function to convert the PDF to a structured set of Markdown files.

    Args:
        pdf_path: Path to the input PDF file
        output_dir: Directory to save the markdown files
        prompt_file: Path to the LLM prompt template file
        max_workers: Maximum number of parallel LLM API calls (default: 4)
    """

    # --- 0. Configure API ---
    google_api_key = os.getenv("GOOGLE_API_KEY")
    llm_model_name = os.getenv("LLM_MODEL_NAME", "gemini-2.5-flash")
    llm_model_text_only = os.getenv("LLM_MODEL_TEXT_ONLY", "gemini-2.5-flash")

    if not google_api_key or google_api_key == "your_api_key_here":
        print("Error: GOOGLE_API_KEY is not set.")
        print("Please create a .env file with your API key (see .env.example)")
        return

    try:
        genai.configure(api_key=google_api_key)
        model_vision = genai.GenerativeModel(llm_model_name)
        model_text = genai.GenerativeModel(llm_model_text_only)
        print(f"Vision model (with images): {llm_model_name}")
        print(f"Text-only model (no images): {llm_model_text_only}")
    except Exception as e:
        print(f"Error: Could not configure Google AI. Check your API key. {e}")
        return

    # Load the prompt template
    prompt_template = load_prompt_template(prompt_file)

    # --- 1. Setup Directories ---
    if not os.path.exists(pdf_path):
        print(f"Error: PDF file not found at '{pdf_path}'")
        return

    img_dir = os.path.join(output_dir, "images")
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(img_dir, exist_ok=True)
    print(f"Output will be saved to '{output_dir}'")
    
    doc = fitz.open(pdf_path)
    
    # --- 2. Get Table of Contents (ToC) ---
    toc = doc.get_toc()
    if not toc:
        print("Error: Could not extract Table of Contents. Aborting.")
        print("This script relies on a ToC to logically chunk the file.")
        return

    print(f"Found {len(toc)} sections in the Table of Contents.")

    # --- 3. Extract Content from All Sections (Sequential) ---
    print("\nPhase 1: Extracting content from sections...")

    # Track which pages have been processed to avoid duplication
    processed_pages = set()

    # Collect all sections to process
    sections_to_process = []

    # Track sections for index.md (includes metadata for TOC structure)
    sections_for_index = []

    for i, entry in enumerate(toc):
        level, title, start_page = entry

        # Page numbers in PyMuPDF ToC are 1-indexed, pages are 0-indexed
        start_page_idx = start_page - 1

        # Determine end page
        if i + 1 < len(toc):
            # End page is the page *before* the next section starts
            end_page_idx = toc[i+1][2] - 2
        else:
            # This is the last section, go to the end of the document
            end_page_idx = doc.page_count - 1

        # Ensure start/end pages are valid (for single-page sections)
        if start_page_idx > end_page_idx:
            end_page_idx = start_page_idx

        # Skip this section if all its pages have already been processed
        pages_in_section = set(range(start_page_idx, end_page_idx + 1))
        new_pages = pages_in_section - processed_pages

        if not new_pages:
            print(f"  Skipping: '{title}' (Pages {start_page_idx + 1} to {end_page_idx + 1}) - already processed")
            continue

        # Only process pages that haven't been seen yet
        start_page_idx = min(new_pages)
        end_page_idx = max(new_pages)

        print(f"  Extracting: '{title}' (Pages {start_page_idx + 1} to {end_page_idx + 1})")

        section_raw_content = ""
        section_filename = sanitize_filename(title)
        page_images = []  # Store rendered page images for multimodal LLM
        image_references = []  # Track image filenames for markdown links

        # 4a. Iterate through all pages in this section
        for page_num in range(start_page_idx, end_page_idx + 1):
            try:
                page = doc.load_page(page_num)
            except Exception as e:
                print(f"  Warning: Could not load page {page_num + 1}. Skipping. Error: {e}")
                continue

            blocks = page.get_text("dict")["blocks"]

            # Extract text content
            for block in blocks:
                if block["type"] == 0:  # This is a text block
                    for line in block["lines"]:
                        for span in line["spans"]:
                            section_raw_content += span["text"] + " "
                        section_raw_content += "\n"

            # Check for and extract embedded images (bitmaps)
            embedded_images_found = False
            for block in blocks:
                if block["type"] == 1:  # This is an embedded image block
                    try:
                        img_xref = block["xref"]
                        if img_xref == 0:
                            continue

                        img = doc.extract_image(img_xref)
                        img_bytes = img["image"]
                        img_ext = img["ext"]

                        img_filename = f"page_{page_num + 1}_img_{img_xref}.{img_ext}"
                        img_path = os.path.join(img_dir, img_filename)

                        with open(img_path, "wb") as img_file:
                            img_file.write(img_bytes)

                        # Load as PIL image for multimodal API
                        pil_image = Image.open(io.BytesIO(img_bytes))
                        page_images.append(pil_image)
                        image_references.append(f"./images/{img_filename}")
                        embedded_images_found = True
                        print(f"    Extracted embedded image: {img_filename}")

                    except Exception as e:
                        print(f"  Warning: Could not extract embedded image on page {page_num + 1}: {e}")

            # Check if page has real diagrams (not just tables/headers)
            # Use smart heuristics to filter false positives
            should_save_diagram = False
            try:
                # Get the page's drawing commands to see if there are vector graphics
                drawings = page.get_drawings()
                if drawings and len(drawings) > 0:
                    is_diagram, reason = is_real_diagram(page, drawings)
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
                    pil_image = Image.open(io.BytesIO(img_data))

                    # Save the rendered page image
                    img_filename = f"page_{page_num + 1}_diagram.png"
                    img_path = os.path.join(img_dir, img_filename)
                    pil_image.save(img_path)

                    # Store for multimodal API and track reference
                    page_images.append(pil_image)
                    image_references.append(f"./images/{img_filename}")
                    print(f"    Rendered full page diagram: {img_filename}")

                except Exception as e:
                    print(f"  Warning: Could not render page {page_num + 1} as image: {e}")

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

        # If file already exists, skip LLM processing but keep in index
        if file_exists:
            print(f"  ✓ Resuming: '{title}' already exists, skipping LLM processing")
        else:
            # Select model: use vision model if we have images, otherwise use text-only model
            if page_images:
                selected_model = model_vision
                model_info = f"vision ({llm_model_name}, {len(page_images)} image(s))"
            else:
                selected_model = model_text
                model_info = f"text-only ({llm_model_text_only})"

            # Collect section data for parallel processing
            sections_to_process.append({
                'title': title,
                'filename': section_filename,
                'raw_content': section_raw_content,
                'page_images': page_images,
                'image_references': image_references,
                'model': selected_model,
                'model_info': model_info
            })

        # Mark these pages as processed
        processed_pages.update(range(start_page_idx, end_page_idx + 1))

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

            formatted_markdown = call_llm_api(
                section_data['raw_content'],
                section_data['title'],
                section_data['model'],
                prompt_template,
                section_data['page_images'],
                section_data['image_references']
            )

            # Write immediately after formatting
            section_md_path = os.path.join(output_dir, filename)
            with open(section_md_path, "w", encoding="utf-8") as f:
                f.write(formatted_markdown)

            print(f"  ✓ Completed and wrote '{title}' -> {filename}", flush=True)
            return (filename, True)

        except Exception as e:
            print(f"  ✗ Error formatting '{section_data['title']}': {e}", flush=True)
            # Write error fallback
            try:
                section_md_path = os.path.join(output_dir, section_data['filename'])
                with open(section_md_path, "w", encoding="utf-8") as f:
                    f.write(f"# {section_data['title']}\n\n[ERROR: {e}]\n\n{section_data['raw_content']}")
                return (section_data['filename'], False)
            except Exception as write_err:
                print(f"  ✗ Could not write error file: {write_err}", flush=True)
                return (section_data['filename'], False)

    # Process all sections in parallel, writing as they complete
    if len(sections_to_process) > 0:
        completed_count = 0
        error_count = 0
        total_sections_to_process = len(sections_to_process)

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
            f.write(f"{indent}* [{title} (Page {page})](./{filename})\n")

    print(f"Index created with {len(sections_for_index)} sections.", flush=True)

    # Summary
    print("\n" + "=" * 60, flush=True)
    print("Conversion Complete!", flush=True)
    print("=" * 60, flush=True)
    print(f"Sections processed:  {completed_count}/{len(sections_to_process)}", flush=True)
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
  Create a .env file with GOOGLE_API_KEY and LLM_MODEL_NAME
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

    args = parser.parse_args()

    print("=" * 60)
    print("PDF to Markdown Converter")
    print("=" * 60)
    print(f"Input PDF:      {args.pdf_path}")
    print(f"Output Dir:     {args.output_dir}")
    print(f"Prompt:         {args.prompt_file}")
    print(f"Max Workers:    {args.max_workers}")
    print("=" * 60)
    print()

    convert_pdf_to_markdown(args.pdf_path, args.output_dir, args.prompt_file, args.max_workers)


if __name__ == "__main__":
    main()