import os
import argparse
import pdfplumber
import fitz  # PyMuPDF
from multiprocessing import Pool, cpu_count
from tqdm import tqdm
import time
import json
from pathlib import Path


def detect_black_rectangles(pdf_path, black_threshold=0.15):
    """
    Detect potential redaction boxes (black rectangles) in a PDF.
    Returns list of rectangles per page: [(page_num, x0, y0, x1, y1), ...]
    """
    redaction_boxes = []
    
    try:
        doc = fitz.open(pdf_path)
        for page_num, page in enumerate(doc):
            # Get all vector graphics (rectangles, paths, etc)
            drawings = page.get_drawings()
            
            for drawing in drawings:
                # Check if this is a filled rectangle
                if drawing.get('type') == 'f':  # filled path
                    rect = drawing.get('rect')
                    color = drawing.get('fill', None)
                    
                    if rect and color:
                        # Check if color is black or very dark
                        # Color is (R, G, B) where each is 0-1
                        if isinstance(color, (list, tuple)) and len(color) >= 3:
                            r, g, b = color[0], color[1], color[2]
                            # Consider black if all RGB components are low
                            if r <= black_threshold and g <= black_threshold and b <= black_threshold:
                                redaction_boxes.append((
                                    page_num,
                                    rect[0], rect[1], rect[2], rect[3]
                                ))
            
            # Also check for filled rectangles using another method
            for item in page.get_text("dict")["blocks"]:
                if item.get("type") == 1:  # Image block (sometimes used for redactions)
                    bbox = item.get("bbox")
                    # Check if it's a solid color image that might be a redaction
                    if bbox:
                        redaction_boxes.append((
                            page_num,
                            bbox[0], bbox[1], bbox[2], bbox[3]
                        ))
        
        doc.close()
    except Exception as e:
        print(f"Error detecting rectangles in {pdf_path}: {e}")
    
    return redaction_boxes


def check_text_under_boxes(pdf_path, redaction_boxes, overlap_threshold=0.5):
    """
    Check if there is text underneath the detected redaction boxes.
    Returns dict: {
        'has_redacted_text': bool,
        'redacted_text_count': int,
        'redacted_chars': list of (page, text, bbox)
    }
    """
    if not redaction_boxes:
        return {
            'has_redacted_text': False,
            'redacted_text_count': 0,
            'redacted_chars': []
        }
    
    redacted_chars = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                # Get all characters with positions
                chars = page.chars
                
                # Get redaction boxes for this page
                page_boxes = [box for box in redaction_boxes if box[0] == page_num]
                
                for char in chars:
                    char_bbox = (
                        float(char.get('x0', 0)),
                        float(char.get('top', 0)),
                        float(char.get('x1', 0)),
                        float(char.get('bottom', 0))
                    )
                    
                    # Check if character overlaps with any redaction box
                    for box in page_boxes:
                        box_rect = (box[1], box[2], box[3], box[4])
                        
                        if rectangles_overlap(char_bbox, box_rect, overlap_threshold):
                            redacted_chars.append((
                                page_num,
                                char.get('text', ''),
                                char_bbox
                            ))
                            break
    
    except Exception as e:
        print(f"Error checking text under boxes in {pdf_path}: {e}")
    
    return {
        'has_redacted_text': len(redacted_chars) > 0,
        'redacted_text_count': len(redacted_chars),
        'redacted_chars': redacted_chars
    }


def rectangles_overlap(bbox1, bbox2, threshold=0.5):
    """
    Check if two bounding boxes overlap significantly.
    bbox format: (x0, y0, x1, y1)
    """
    x0_1, y0_1, x1_1, y1_1 = bbox1
    x0_2, y0_2, x1_2, y1_2 = bbox2
    
    # Calculate intersection
    x0_i = max(x0_1, x0_2)
    y0_i = max(y0_1, y0_2)
    x1_i = min(x1_1, x1_2)
    y1_i = min(y1_1, y1_2)
    
    if x0_i >= x1_i or y0_i >= y1_i:
        return False  # No overlap
    
    # Calculate areas
    intersection_area = (x1_i - x0_i) * (y1_i - y0_i)
    bbox1_area = (x1_1 - x0_1) * (y1_1 - y0_1)
    
    if bbox1_area == 0:
        return False
    
    # Check if intersection is significant
    overlap_ratio = intersection_area / bbox1_area
    return overlap_ratio >= threshold


def analyze_pdf_for_redactions(pdf_path):
    """
    Analyze a single PDF to determine if it has recoverable redacted text.
    Returns dict with analysis results.
    """
    result = {
        'path': pdf_path,
        'filename': os.path.basename(pdf_path),
        'has_redaction_boxes': False,
        'has_recoverable_text': False,
        'redaction_box_count': 0,
        'redacted_char_count': 0,
        'should_process': False,
        'error': None
    }
    
    try:
        # Step 1: Detect redaction boxes
        redaction_boxes = detect_black_rectangles(pdf_path)
        result['has_redaction_boxes'] = len(redaction_boxes) > 0
        result['redaction_box_count'] = len(redaction_boxes)
        
        if not result['has_redaction_boxes']:
            return result
        
        # Step 2: Check for text under boxes
        text_check = check_text_under_boxes(pdf_path, redaction_boxes)
        result['has_recoverable_text'] = text_check['has_redacted_text']
        result['redacted_char_count'] = text_check['redacted_text_count']
        
        # Should process if has both redaction boxes and recoverable text
        result['should_process'] = result['has_redaction_boxes'] and result['has_recoverable_text']
        
    except Exception as e:
        result['error'] = str(e)
    
    return result


def scan_directory_for_redactions(directory, recursive=True, workers=None):
    """
    Scan a directory for PDFs with recoverable redacted text.
    Returns list of analysis results.
    """
    if workers is None:
        workers = max(1, cpu_count() - 1)
    
    # Find all PDF files
    pdf_files = []
    if recursive:
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.lower().endswith('.pdf'):
                    pdf_files.append(os.path.join(root, file))
    else:
        pdf_files = [
            os.path.join(directory, f) 
            for f in os.listdir(directory) 
            if f.lower().endswith('.pdf')
        ]
    
    if not pdf_files:
        print(f"No PDF files found in {directory}")
        return []
    
    print(f"\nFound {len(pdf_files)} PDF files")
    print(f"Analyzing for redactions using {workers} workers...\n")
    
    # Analyze PDFs in parallel
    with Pool(processes=workers) as pool:
        results = list(tqdm(
            pool.imap(analyze_pdf_for_redactions, pdf_files),
            total=len(pdf_files),
            desc="Scanning PDFs",
            unit="file"
        ))
    
    return results


def create_highlighted_output(pdf_path, output_path, redaction_boxes, highlight_color=(1, 1, 0)):
    """
    Create output PDF with highlighted redacted areas.
    Yellow highlighting shows where recoverable text was found under redactions.
    """
    doc = fitz.open(pdf_path)
    
    # Group boxes by page
    boxes_by_page = {}
    for box in redaction_boxes:
        page_num = box[0]
        if page_num not in boxes_by_page:
            boxes_by_page[page_num] = []
        boxes_by_page[page_num].append(box[1:])  # Just the coordinates
    
    # Highlight redaction areas
    for page_num, page in enumerate(doc):
        if page_num in boxes_by_page:
            for box_coords in boxes_by_page[page_num]:
                rect = fitz.Rect(box_coords)
                # Add semi-transparent yellow highlight
                highlight = page.add_highlight_annot(rect)
                highlight.set_colors(stroke=highlight_color)
                highlight.set_opacity(0.3)
                highlight.update()
    
    doc.save(output_path)
    doc.close()


def process_redacted_pdfs(analysis_results, output_dir=None, mode="highlight", workers=None):
    """
    Process only PDFs that have recoverable redacted text.
    """
    # Filter to only PDFs that should be processed
    to_process = [r for r in analysis_results if r['should_process']]
    
    if not to_process:
        print("\n❌ No PDFs found with recoverable redacted text")
        return
    
    print(f"\n✅ Found {len(to_process)} PDF(s) with recoverable redacted text")
    print(f"📊 Summary:")
    print(f"   - Total scanned: {len(analysis_results)}")
    print(f"   - With redaction boxes: {sum(1 for r in analysis_results if r['has_redaction_boxes'])}")
    print(f"   - With recoverable text: {len(to_process)}")
    print(f"   - Will process: {len(to_process)}\n")
    
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    # Process each file
    for idx, result in enumerate(to_process, 1):
        input_pdf = result['path']
        print(f"[{idx}/{len(to_process)}] Processing: {result['filename']}")
        print(f"   Redacted characters found: {result['redacted_char_count']}")
        
        # Determine output path
        if output_dir:
            output_pdf = os.path.join(
                output_dir,
                f"{Path(result['filename']).stem}_unredacted.pdf"
            )
        else:
            base, _ = os.path.splitext(input_pdf)
            output_pdf = f"{base}_unredacted.pdf"
        
        try:
            if mode == "highlight":
                # Just highlight the redaction areas
                redaction_boxes = detect_black_rectangles(input_pdf)
                create_highlighted_output(input_pdf, output_pdf, redaction_boxes)
                print(f"   ✓ Created highlighted version: {output_pdf}")
            else:
                # Use the original side-by-side or overlay method
                # Import from optimized script
                from redact_extract_optimized import make_side_by_side_optimized, make_overlay_white_optimized
                
                if mode == "side_by_side":
                    make_side_by_side_optimized(input_pdf, output_pdf, workers=workers)
                else:
                    make_overlay_white_optimized(input_pdf, output_pdf, workers=workers)
        
        except Exception as e:
            print(f"   ❌ Error: {e}")


def save_analysis_report(results, output_file):
    """
    Save analysis results to JSON file.
    """
    report = {
        'total_files': len(results),
        'files_with_redaction_boxes': sum(1 for r in results if r['has_redaction_boxes']),
        'files_with_recoverable_text': sum(1 for r in results if r['has_recoverable_text']),
        'files_to_process': sum(1 for r in results if r['should_process']),
        'files': results
    }
    
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n📄 Analysis report saved to: {output_file}")


def main():
    ap = argparse.ArgumentParser(
        description="Detect and recover text from improperly redacted PDFs"
    )
    ap.add_argument("input", help="PDF file or directory to scan")
    ap.add_argument("-o", "--output", default=None,
                    help="Output directory for processed PDFs")
    ap.add_argument("--mode", choices=["highlight", "side_by_side", "overlay_white"],
                    default="highlight",
                    help="Output mode: highlight redactions, side-by-side, or white overlay")
    ap.add_argument("--scan-only", action="store_true",
                    help="Only scan and report, don't process files")
    ap.add_argument("--recursive", "-r", action="store_true", default=True,
                    help="Recursively scan subdirectories")
    ap.add_argument("--workers", type=int, default=None,
                    help=f"Number of parallel workers (default: {max(1, cpu_count()-1)})")
    ap.add_argument("--report", default=None,
                    help="Save analysis report to JSON file")
    args = ap.parse_args()
    
    start_time = time.time()
    
    # Determine if input is file or directory
    if os.path.isfile(args.input):
        print(f"Analyzing single file: {args.input}\n")
        results = [analyze_pdf_for_redactions(args.input)]
    elif os.path.isdir(args.input):
        results = scan_directory_for_redactions(
            args.input,
            recursive=args.recursive,
            workers=args.workers
        )
    else:
        print(f"❌ Input not found: {args.input}")
        return
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"SCAN RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"Total PDFs scanned: {len(results)}")
    print(f"PDFs with redaction boxes: {sum(1 for r in results if r['has_redaction_boxes'])}")
    print(f"PDFs with recoverable text: {sum(1 for r in results if r['has_recoverable_text'])}")
    print(f"PDFs to process: {sum(1 for r in results if r['should_process'])}")
    
    # Show files with recoverable text
    processable = [r for r in results if r['should_process']]
    if processable:
        print(f"\n📋 Files with recoverable redacted text:")
        for r in processable:
            print(f"   • {r['filename']} ({r['redacted_char_count']} chars)")
    
    print(f"{'='*60}\n")
    
    # Save report if requested
    if args.report:
        save_analysis_report(results, args.report)
    
    # Process files if not scan-only
    if not args.scan_only:
        process_redacted_pdfs(
            results,
            output_dir=args.output,
            mode=args.mode,
            workers=args.workers
        )
    
    total_time = time.time() - start_time
    print(f"\n⏱️  Total execution time: {total_time:.2f}s")


if __name__ == "__main__":
    main()
