import os
import random
import fitz  # PyMuPDF
import pdfplumber
from pathlib import Path
import json
from tqdm import tqdm


def get_page_count(pdf_path):
    """Get number of pages in a PDF."""
    try:
        doc = fitz.open(pdf_path)
        count = len(doc)
        doc.close()
        return count
    except:
        return None


def find_all_pdfs(directory):
    """Find all PDF files recursively."""
    pdfs = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.lower().endswith('.pdf'):
                pdfs.append(os.path.join(root, file))
    return pdfs


def get_black_boxes(pdf_path, black_threshold=0.2):
    """Extract black boxes from PDF."""
    boxes = []
    try:
        doc = fitz.open(pdf_path)
        for page_num, page in enumerate(doc):
            drawings = page.get_drawings()
            for drawing in drawings:
                color = drawing.get('fill', None)
                rect = drawing.get('rect', None)
                if color and rect and isinstance(color, (list, tuple)) and len(color) >= 3:
                    r, g, b = color[0], color[1], color[2]
                    if r <= black_threshold and g <= black_threshold and b <= black_threshold:
                        boxes.append({
                            'page': page_num,
                            'x0': rect[0], 'y0': rect[1],
                            'x1': rect[2], 'y1': rect[3]
                        })
        doc.close()
    except:
        pass
    return boxes


def get_text_positions(pdf_path):
    """Extract character positions."""
    chars = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                page_chars = page.chars
                for char in page_chars:
                    chars.append({
                        'page': page_num,
                        'text': char.get('text', ''),
                        'x0': float(char.get('x0', 0)),
                        'y0': float(char.get('top', 0)),
                        'x1': float(char.get('x1', 0)),
                        'y1': float(char.get('bottom', 0))
                    })
    except:
        pass
    return chars


def boxes_overlap(box1, box2, threshold=0.3):
    """Check if boxes overlap."""
    x0_i = max(box1['x0'], box2['x0'])
    y0_i = max(box1['y0'], box2['y0'])
    x1_i = min(box1['x1'], box2['x1'])
    y1_i = min(box1['y1'], box2['y1'])
    
    if x0_i >= x1_i or y0_i >= y1_i:
        return False
    
    intersection = (x1_i - x0_i) * (y1_i - y0_i)
    char_area = (box2['x1'] - box2['x0']) * (box2['y1'] - box2['y0'])
    
    return (intersection / char_area) >= threshold if char_area > 0 else False


def test_pdf_quick(pdf_path):
    """Quick test for improper redactions."""
    result = {
        'path': pdf_path,
        'filename': os.path.basename(pdf_path),
        'pages': 0,
        'black_boxes': 0,
        'boxes_with_text': 0,
        'recoverable_chars': 0,
        'has_improper_redactions': False,
        'error': None
    }
    
    try:
        # Get page count
        result['pages'] = get_page_count(pdf_path)
        
        # Find black boxes
        black_boxes = get_black_boxes(pdf_path)
        result['black_boxes'] = len(black_boxes)
        
        if not black_boxes:
            return result
        
        # Get text positions
        text_chars = get_text_positions(pdf_path)
        
        if not text_chars:
            return result
        
        # Check overlaps
        overlaps = []
        for box in black_boxes:
            page_chars = [c for c in text_chars if c['page'] == box['page']]
            box_chars = [c for c in page_chars if boxes_overlap(box, c)]
            if box_chars:
                overlaps.append(len(box_chars))
        
        result['boxes_with_text'] = len(overlaps)
        result['recoverable_chars'] = sum(overlaps)
        result['has_improper_redactions'] = result['boxes_with_text'] > 0
        
    except Exception as e:
        result['error'] = str(e)
    
    return result


def main():
    print("="*80)
    print("RANDOM PDF SAMPLE TEST - Improper Redaction Detection")
    print("="*80)
    
    base_dir = r"C:\Users\mackp\Documents\Ep"
    
    # Step 1: Find all PDFs
    print("\nStep 1: Finding all PDFs...")
    all_pdfs = find_all_pdfs(base_dir)
    print(f"  Found {len(all_pdfs)} total PDFs")
    
    # Step 2: Filter by page count
    print("\nStep 2: Filtering PDFs under 100 pages...")
    filtered_pdfs = []
    
    for pdf in tqdm(all_pdfs, desc="Checking page counts", unit="file"):
        page_count = get_page_count(pdf)
        if page_count and 1 <= page_count < 100:
            filtered_pdfs.append({'path': pdf, 'pages': page_count})
    
    print(f"  Found {len(filtered_pdfs)} PDFs under 100 pages")
    
    if len(filtered_pdfs) < 50:
        print(f"  Warning: Only {len(filtered_pdfs)} PDFs available")
        sample_size = len(filtered_pdfs)
    else:
        sample_size = 50
    
    # Step 3: Random sample
    print(f"\nStep 3: Randomly selecting {sample_size} PDFs...")
    sample = random.sample(filtered_pdfs, sample_size)
    
    # Step 4: Test each PDF
    print(f"\nStep 4: Testing {sample_size} PDFs for improper redactions...\n")
    results = []
    
    for item in tqdm(sample, desc="Testing PDFs", unit="file"):
        result = test_pdf_quick(item['path'])
        results.append(result)
    
    # Step 5: Summary
    print("\n" + "="*80)
    print("RESULTS SUMMARY")
    print("="*80)
    
    total_tested = len(results)
    with_black_boxes = sum(1 for r in results if r['black_boxes'] > 0)
    with_improper = sum(1 for r in results if r['has_improper_redactions'])
    total_recoverable = sum(r['recoverable_chars'] for r in results)
    
    print(f"\nTotal PDFs tested: {total_tested}")
    print(f"PDFs with black boxes: {with_black_boxes}")
    print(f"PDFs with IMPROPER redactions: {with_improper}")
    print(f"Total recoverable characters: {total_recoverable:,}")
    
    if with_improper > 0:
        print(f"\n✅ Found {with_improper} PDFs with recoverable redacted text!\n")
        print("Improperly redacted files:")
        print("-" * 80)
        
        for r in results:
            if r['has_improper_redactions']:
                print(f"\n  📄 {r['filename']}")
                print(f"     Pages: {r['pages']}")
                print(f"     Black boxes: {r['black_boxes']}")
                print(f"     Boxes with text: {r['boxes_with_text']}")
                print(f"     Recoverable chars: {r['recoverable_chars']:,}")
    else:
        print("\n❌ No improperly redacted PDFs found in this sample")
    
    # Save results to JSON
    output_file = "random_sample_results.json"
    report = {
        'sample_size': sample_size,
        'total_tested': total_tested,
        'with_black_boxes': with_black_boxes,
        'with_improper_redactions': with_improper,
        'total_recoverable_chars': total_recoverable,
        'files': results
    }
    
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n📄 Full report saved to: {output_file}")
    print("=" * 80)


if __name__ == "__main__":
    main()
