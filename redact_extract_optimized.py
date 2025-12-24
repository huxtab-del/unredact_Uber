import os
import argparse
import pdfplumber
import fitz  # PyMuPDF
from multiprocessing import Pool, cpu_count
from functools import partial
from tqdm import tqdm
import time


def group_words_into_lines(words, line_tol=2.0):
    """Cluster words into lines using their 'top' coordinate."""
    if not words:
        return []

    words = sorted(words, key=lambda w: (float(w.get("top", 0.0)), float(w.get("x0", 0.0))))

    lines = []
    current = []
    current_top = None

    for w in words:
        top = float(w.get("top", 0.0))
        if current_top is None:
            current_top = top
            current = [w]
            continue

        if abs(top - current_top) <= line_tol:
            current.append(w)
            # running average stabilizes grouping
            current_top = (current_top * (len(current) - 1) + top) / len(current)
        else:
            lines.append(current)
            current = [w]
            current_top = top

    if current:
        lines.append(current)

    return lines


def build_line_text(line_words, space_unit_pts=3.0, min_spaces=1):
    """
    Rebuild a line by inserting spaces based on x-gaps.
    Returns (text, x0, x1, top, font_size_est).
    """
    line_words = sorted(line_words, key=lambda w: float(w.get("x0", 0.0)))

    # representative font size: median of sizes if present, else bbox height
    sizes = []
    for w in line_words:
        s = w.get("size", None)
        if s is not None:
            try:
                sizes.append(float(s))
            except Exception:
                pass

    if sizes:
        sizes_sorted = sorted(sizes)
        font_size = float(sizes_sorted[len(sizes_sorted) // 2])
    else:
        # fallback: median bbox height
        hs = []
        for w in line_words:
            top = float(w.get("top", 0.0))
            bottom = float(w.get("bottom", top + 10.0))
            hs.append(max(6.0, bottom - top))
        hs.sort()
        font_size = float(hs[len(hs) // 2]) if hs else 10.0

    top_med = sorted([float(w.get("top", 0.0)) for w in line_words])[len(line_words) // 2]

    first_x0 = float(line_words[0].get("x0", 0.0))
    last_x1 = float(line_words[0].get("x1", line_words[0].get("x0", 0.0)))
    prev_x1 = float(line_words[0].get("x1", line_words[0].get("x0", 0.0)))

    parts = [line_words[0].get("text", "")]

    for w in line_words[1:]:
        text = w.get("text", "")
        x0 = float(w.get("x0", 0.0))
        x1 = float(w.get("x1", x0))

        gap = x0 - prev_x1

        if gap > 0:
            n_spaces = int(round(gap / max(0.5, space_unit_pts)))
            n_spaces = max(min_spaces, n_spaces)
            parts.append(" " * n_spaces)
        else:
            # slight negative gaps happen; keep minimal separation only when it looks like a break
            parts.append(" " if gap > -space_unit_pts * 0.3 else "")

        parts.append(text)
        prev_x1 = max(prev_x1, x1)
        last_x1 = max(last_x1, x1)

    return "".join(parts), first_x0, last_x1, top_med, font_size


def process_single_page(args):
    """
    Process a single page - designed for parallel execution.
    Returns: (page_num, page_lines, page_rect_dict)
    """
    page_num, pdf_path, line_tol, space_unit_pts, min_spaces = args
    
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_num]
        words = page.extract_words(
            keep_blank_chars=False,
            use_text_flow=False,
            extra_attrs=["size", "fontname"]
        )
        
        # Get page dimensions
        page_rect = {
            'width': page.width,
            'height': page.height
        }

    lines = group_words_into_lines(words, line_tol=line_tol)

    out = []
    for lw in lines:
        line_text, x0, x1, top, font_size = build_line_text(
            lw, space_unit_pts=space_unit_pts, min_spaces=min_spaces
        )
        if line_text.strip():
            out.append((line_text, x0, top, font_size))
    
    return (page_num, out, page_rect)


def extract_lines_parallel(pdf_path, line_tol=2.0, space_unit_pts=3.0, min_spaces=1, workers=None):
    """
    Extract lines from all pages using parallel processing.
    Returns list per page: [(line_text, x0, top, font_size), ...]
    """
    if workers is None:
        workers = max(1, cpu_count() - 1)  # Leave one core free
    
    # Get page count
    with pdfplumber.open(pdf_path) as pdf:
        num_pages = len(pdf.pages)
    
    # Prepare arguments for parallel processing
    args_list = [
        (i, pdf_path, line_tol, space_unit_pts, min_spaces)
        for i in range(num_pages)
    ]
    
    # Process pages in parallel
    pages_lines = [None] * num_pages
    page_rects = [None] * num_pages
    
    with Pool(processes=workers) as pool:
        results = list(tqdm(
            pool.imap(process_single_page, args_list),
            total=num_pages,
            desc="Extracting text",
            unit="page"
        ))
    
    # Reassemble results in order
    for page_num, lines, rect in results:
        pages_lines[page_num] = lines
        page_rects[page_num] = rect
    
    return pages_lines, page_rects


def make_side_by_side_optimized(input_pdf, output_pdf, line_tol=2.0, space_unit_pts=3.0, min_spaces=1, workers=None):
    """
    Optimized version: parallel text extraction, single PDF open for rendering.
    """
    print(f"Processing: {input_pdf}")
    start_time = time.time()
    
    # Extract text in parallel
    lines_per_page, page_rects = extract_lines_parallel(
        input_pdf, line_tol=line_tol, space_unit_pts=space_unit_pts, 
        min_spaces=min_spaces, workers=workers
    )
    
    extract_time = time.time() - start_time
    print(f"Text extraction completed in {extract_time:.2f}s")
    
    # Render output
    render_start = time.time()
    src = fitz.open(input_pdf)
    out = fitz.open()

    for i, src_page in enumerate(tqdm(src, desc="Rendering pages", unit="page")):
        rect = src_page.rect
        w, h = rect.width, rect.height

        new_page = out.new_page(width=2 * w, height=h)

        # Left: embed original page as a vector "form"
        new_page.show_pdf_page(fitz.Rect(0, 0, w, h), src, i)

        # Right: draw rebuilt text
        x_off = w
        page_lines = lines_per_page[i] if i < len(lines_per_page) else []

        for (txt, x0, top, font_size) in page_lines:
            # y: pdfplumber 'top' is top of bbox; nudge toward baseline
            y = float(top) + float(font_size) * 0.85

            new_page.insert_text(
                fitz.Point(x_off + float(x0), float(y)),
                txt,
                fontsize=float(font_size),
                fontname="helv",     # built-in Helvetica
                color=(0, 0, 0),     # black
                overlay=True
            )

    out.save(output_pdf)
    out.close()
    src.close()
    
    render_time = time.time() - render_start
    total_time = time.time() - start_time
    
    print(f"Rendering completed in {render_time:.2f}s")
    print(f"Total processing time: {total_time:.2f}s")
    print(f"Wrote: {output_pdf}")


def make_overlay_white_optimized(input_pdf, output_pdf, line_tol=2.0, space_unit_pts=3.0, min_spaces=1, workers=None):
    """
    Optimized version: parallel text extraction.
    """
    print(f"Processing: {input_pdf}")
    start_time = time.time()
    
    # Extract text in parallel
    lines_per_page, _ = extract_lines_parallel(
        input_pdf, line_tol=line_tol, space_unit_pts=space_unit_pts, 
        min_spaces=min_spaces, workers=workers
    )
    
    extract_time = time.time() - start_time
    print(f"Text extraction completed in {extract_time:.2f}s")
    
    # Render output
    render_start = time.time()
    doc = fitz.open(input_pdf)

    for i, page in enumerate(tqdm(doc, desc="Rendering pages", unit="page")):
        page_lines = lines_per_page[i] if i < len(lines_per_page) else []
        for (txt, x0, top, font_size) in page_lines:
            y = float(top) + float(font_size) * 0.85
            page.insert_text(
                fitz.Point(float(x0), float(y)),
                txt,
                fontsize=float(font_size),
                fontname="helv",
                color=(1, 1, 1),   # white
                overlay=True
            )

    doc.save(output_pdf)
    doc.close()
    
    render_time = time.time() - render_start
    total_time = time.time() - start_time
    
    print(f"Rendering completed in {render_time:.2f}s")
    print(f"Total processing time: {total_time:.2f}s")
    print(f"Wrote: {output_pdf}")


def batch_process(input_files, output_dir=None, mode="side_by_side", line_tol=2.0, 
                  space_unit_pts=3.0, min_spaces=1, workers=None):
    """
    Process multiple PDF files in batch.
    """
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    print(f"\nBatch processing {len(input_files)} files...")
    print(f"Using {workers or max(1, cpu_count() - 1)} worker processes\n")
    
    total_start = time.time()
    
    for idx, input_pdf in enumerate(input_files, 1):
        print(f"\n[{idx}/{len(input_files)}] Processing: {os.path.basename(input_pdf)}")
        
        if not os.path.exists(input_pdf):
            print(f"  ⚠️  File not found: {input_pdf}")
            continue
        
        # Determine output path
        base, _ = os.path.splitext(os.path.basename(input_pdf))
        suffix = "_side_by_side.pdf" if mode == "side_by_side" else "_overlay_white.pdf"
        
        if output_dir:
            output_pdf = os.path.join(output_dir, base + suffix)
        else:
            output_pdf = os.path.join(os.path.dirname(input_pdf), base + suffix)
        
        try:
            if mode == "side_by_side":
                make_side_by_side_optimized(
                    input_pdf, output_pdf,
                    line_tol=line_tol, space_unit_pts=space_unit_pts, 
                    min_spaces=min_spaces, workers=workers
                )
            else:
                make_overlay_white_optimized(
                    input_pdf, output_pdf,
                    line_tol=line_tol, space_unit_pts=space_unit_pts, 
                    min_spaces=min_spaces, workers=workers
                )
        except Exception as e:
            print(f"  ❌ Error processing {input_pdf}: {e}")
    
    total_time = time.time() - total_start
    print(f"\n✅ Batch processing completed in {total_time:.2f}s")
    print(f"Average time per file: {total_time/len(input_files):.2f}s")


def main():
    ap = argparse.ArgumentParser(
        description="High-throughput PDF redaction text recovery tool with parallel processing"
    )
    ap.add_argument("input", nargs="+", help="Path(s) to input PDF file(s)")
    ap.add_argument("-o", "--output", default=None, 
                    help="Output PDF path (single file) or directory (batch mode)")
    ap.add_argument("--mode", choices=["side_by_side", "overlay_white"], 
                    default="side_by_side")
    ap.add_argument("--line-tol", type=float, default=2.0, 
                    help="Line grouping tolerance (pts). Try 1.5–4.0")
    ap.add_argument("--space-unit", type=float, default=3.0, 
                    help="Pts per inserted space (bigger => fewer spaces)")
    ap.add_argument("--min-spaces", type=int, default=1, 
                    help="Minimum spaces between words when gap exists")
    ap.add_argument("--workers", type=int, default=None,
                    help=f"Number of parallel workers (default: {max(1, cpu_count()-1)})")
    ap.add_argument("--batch", action="store_true",
                    help="Batch mode: process multiple files")
    args = ap.parse_args()

    # Validate input files
    input_files = []
    for path in args.input:
        if os.path.isfile(path):
            input_files.append(path)
        elif os.path.isdir(path):
            # Find all PDFs in directory
            pdfs = [os.path.join(path, f) for f in os.listdir(path) if f.lower().endswith('.pdf')]
            input_files.extend(pdfs)
        else:
            print(f"⚠️  Not found: {path}")
    
    if not input_files:
        print("❌ No valid PDF files found")
        return
    
    # Batch mode or single file
    if len(input_files) > 1 or args.batch:
        batch_process(
            input_files,
            output_dir=args.output,
            mode=args.mode,
            line_tol=args.line_tol,
            space_unit_pts=args.space_unit,
            min_spaces=args.min_spaces,
            workers=args.workers
        )
    else:
        # Single file processing
        input_pdf = input_files[0]
        
        if args.output is None:
            base, _ = os.path.splitext(input_pdf)
            suffix = "_side_by_side.pdf" if args.mode == "side_by_side" else "_overlay_white.pdf"
            args.output = base + suffix
        
        if args.mode == "side_by_side":
            make_side_by_side_optimized(
                input_pdf, args.output,
                line_tol=args.line_tol, space_unit_pts=args.space_unit, 
                min_spaces=args.min_spaces, workers=args.workers
            )
        else:
            make_overlay_white_optimized(
                input_pdf, args.output,
                line_tol=args.line_tol, space_unit_pts=args.space_unit, 
                min_spaces=args.min_spaces, workers=args.workers
            )


if __name__ == "__main__":
    main()
