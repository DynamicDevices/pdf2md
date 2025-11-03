import fitz  # PyMuPDF
import os
import re
import google.generativeai as genai
import time
import argparse
from dotenv import load_dotenv
from PIL import Image
import io

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


def call_llm_api(raw_content, title, model, prompt_template, page_images=None, image_references=None):
    """
    Uses the Google Generative AI (Gemini) API to format raw text into markdown.

    Args:
        raw_content: Raw text extracted from PDF
        title: Section title
        model: Gemini model instance
        prompt_template: Prompt template string
        page_images: Optional list of PIL Image objects for multimodal processing
        image_references: Optional list of image file paths for markdown links
    """

    # Format image references for the prompt
    image_refs_text = ""
    if image_references:
        image_refs_text = "\n\nAvailable page images for this section:\n"
        for i, ref in enumerate(image_references):
            image_refs_text += f"  - Image {i+1}: {ref}\n"

    llm_prompt = prompt_template.format(title=title, raw_content=raw_content, image_references=image_refs_text)

    try:
        print(f"  (Gemini API) Sending to format: {title}")

        # If we have page images, send them along with the text for better diagram understanding
        if page_images:
            content_parts = [llm_prompt]
            content_parts.extend(page_images)
            response = model.generate_content(content_parts)
        else:
            response = model.generate_content(llm_prompt)

        # Add a small delay to avoid hitting rate limits on rapid, small sections
        time.sleep(1)

        # Strip markdown code fences if present
        result = strip_markdown_fence(response.text)
        return result
    except Exception as e:
        print(f"  ERROR: LLM API call failed for '{title}': {e}")
        # Fallback to simple formatting on error
        fallback_content = f"# {title}\n\n[LLM_API_ERROR: {e}]\n\n"

        # Clean up page markers
        footer_pattern = re.compile(r"\n--- End of Page \d+ ---\n")
        fallback_content += re.sub(footer_pattern, "\n\n", raw_content)

        return fallback_content


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


def convert_pdf_to_markdown(pdf_path, output_dir, prompt_file="prompt.txt"):
    """
    Main function to convert the PDF to a structured set of Markdown files.

    Args:
        pdf_path: Path to the input PDF file
        output_dir: Directory to save the markdown files
        prompt_file: Path to the LLM prompt template file
    """

    # --- 0. Configure API ---
    google_api_key = os.getenv("GOOGLE_API_KEY")
    llm_model_name = os.getenv("LLM_MODEL_NAME", "gemini-1.5-flash")

    if not google_api_key or google_api_key == "your_api_key_here":
        print("Error: GOOGLE_API_KEY is not set.")
        print("Please create a .env file with your API key (see .env.example)")
        return

    try:
        genai.configure(api_key=google_api_key)
        model = genai.GenerativeModel(llm_model_name)
        print(f"Successfully configured Gemini model: {llm_model_name}")
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

    # --- 3. Create Master index.md ---
    index_md_path = os.path.join(output_dir, "index.md")
    with open(index_md_path, "w", encoding="utf-8") as f:
        f.write("# Technical Reference Manual - Index\n\n")
        f.write("This document provides a top-level index for the converted technical manual.\n\n")
        
        for entry in toc:
            level, title, page = entry
            indent = "  " * (level - 1)
            filename = sanitize_filename(title)
            # Link to the markdown file
            f.write(f"{indent}* [{title} (Page {page})](./{filename})\n")

    print(f"Master 'index.md' created.")
    
    # --- 4. Process Each Document Section ---
    print("\nStarting section processing...")
    
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
            
        print(f"\nProcessing: '{title}' (Pages {start_page_idx + 1} to {end_page_idx + 1})")

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

        # 4c. Format content (using the real LLM with page images for diagram context)
        if not section_raw_content.strip():
             print(f"  Skipping '{title}' - no content extracted.")
             continue

        formatted_markdown = call_llm_api(section_raw_content, title, model, prompt_template, page_images, image_references)
        
        # 4d. Save the final Markdown file for this section
        section_md_path = os.path.join(output_dir, section_filename)
        with open(section_md_path, "w", encoding="utf-8") as f:
            f.write(formatted_markdown)

    doc.close()
    print("\n--- Conversion Complete! ---")
    print(f"All files saved in '{output_dir}'.")
    print(f"Start by opening '{index_md_path}' to navigate your new files.")


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

    args = parser.parse_args()

    print("=" * 60)
    print("PDF to Markdown Converter")
    print("=" * 60)
    print(f"Input PDF:  {args.pdf_path}")
    print(f"Output Dir: {args.output_dir}")
    print(f"Prompt:     {args.prompt_file}")
    print("=" * 60)
    print()

    convert_pdf_to_markdown(args.pdf_path, args.output_dir, args.prompt_file)


if __name__ == "__main__":
    main()