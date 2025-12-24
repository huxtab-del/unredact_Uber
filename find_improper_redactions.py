import os
import fitz
import pdfplumber
from tqdm import tqdm
import json
from multiprocessing import Pool, cpu_count


def get_black_boxes(pdf_path):
    """Extract black boxes."""
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
                    if r <= 0.2 and g <= 0.2 and b <= 0.2:
                        boxes.append({'page': page_num, 'x0': rect[0], 'y0': rect[1], 'x1': rect[2], 'y1': rect[3]})
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
                for char in page.chars:
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
    """Check overlap."""
    x0_i = max(box1['x0'], box2['x0'])
    y0_i = max(box1['y0'], box2['y0'])
    x1_i = min(box1['x1'], box2['x1'])
    y1_i = min(box1['y1'], box2['y1'])
    
    if x0_i >= x1_i or y0_i >= y1_i:
        return False
    
    intersection = (x1_i - x0_i) * (y1_i - y0_i)
    char_area = (box2['x1'] - box2['x0']) * (box2['y1'] - box2['y0'])
    return (intersection / char_area) >= threshold if char_area > 0 else False


def test_pdf(pdf_path):
    """Test for improper redactions."""
    black_boxes = get_black_boxes(pdf_path)
    if not black_boxes:
        return None
    
    text_chars = get_text_positions(pdf_path)
    if not text_chars:
        return None
    
    # Check overlaps
    recoverable_text = []
    for box in black_boxes:
        page_chars = [c for c in text_chars if c['page'] == box['page']]
        box_chars = [c for c in page_chars if boxes_overlap(box, c)]
        if box_chars:
            text = ''.join([c['text'] for c in box_chars])
            recoverable_text.append({
                'page': box['page'],
                'text': text,
                'char_count': len(box_chars)
            })
    
    if recoverable_text:
        return {
            'path': pdf_path,
            'filename': os.path.basename(pdf_path),
            'black_boxes': len(black_boxes),
            'recoverable_areas': len(recoverable_text),
            'total_chars': sum(r['char_count'] for r in recoverable_text),
            'sample_text': recoverable_text[:5]
        }
    
    return None


def find_pdfs_in_directory(directory, exclude_patterns=['DataSet']):
    """Find PDFs excluding certain patterns."""
    pdfs = []
    for root, dirs, files in os.walk(directory):
        # Skip excluded directories
        if any(pattern in root for pattern in exclude_patterns):
            continue
        
        for file in files:
            if file.lower().endswith('.pdf'):
                pdfs.append(os.path.join(root, file))
    
    return pdfs


def main():
    print("="*80)
    print("TARGETED SCAN - Finding Improperly Redacted PDFs (PARALLEL)")
    print("="*80)
    
    base_dir = r"C:\Users\mackp\Documents\Ep"
    workers = max(1, cpu_count() - 1)
    
    # Find PDFs excluding DataSet folders
    print(f"\nSearching for PDFs (excluding DataSet folders)...")
    pdfs = find_pdfs_in_directory(base_dir, exclude_patterns=['DataSet'])
    print(f"Found {len(pdfs)} PDFs to scan")
    print(f"Using {workers} parallel workers\n")
    
    # Test each PDF in parallel
    print("Scanning for improper redactions...\n")
    
    with Pool(processes=workers) as pool:
        results = list(tqdm(
            pool.imap(test_pdf, pdfs),
            total=len(pdfs),
            desc="Testing PDFs",
            unit="file"
        ))
    
    # Filter out None results
    improper_redactions = [r for r in results if r is not None]
    
    # Results
    print("\n" + "="*80)
    print("RESULTS")
    print("="*80)
    
    if improper_redactions:
        print(f"\n✅ FOUND {len(improper_redactions)} IMPROPERLY REDACTED PDF(S)!\n")
        
        for i, result in enumerate(improper_redactions, 1):
            print(f"{i}. {result['filename']}")
            print(f"   Path: {result['path']}")
            print(f"   Black boxes: {result['black_boxes']}")
            print(f"   Recoverable areas: {result['recoverable_areas']}")
            print(f"   Total recoverable characters: {result['total_chars']:,}")
            print(f"\n   Sample recovered text:")
            for sample in result['sample_text']:
                print(f"     Page {sample['page']}: \"{sample['text'][:80]}...\"")
            print()
        
        # Save results
        with open('improper_redactions_found.json', 'w') as f:
            json.dump(improper_redactions, f, indent=2)
        
        print(f"📄 Full results saved to: improper_redactions_found.json")
    else:
        print("\n❌ No improperly redacted PDFs found in this scan\n")
    
    print("="*80)


if __name__ == "__main__":
    main()
