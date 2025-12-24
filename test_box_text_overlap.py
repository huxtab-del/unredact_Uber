import fitz  # PyMuPDF
import pdfplumber
import sys


def get_black_boxes(pdf_path, black_threshold=0.2):
    """
    Extract bounding boxes of black rectangles/shapes.
    Returns: [(page_num, x0, y0, x1, y1), ...]
    """
    boxes = []
    doc = fitz.open(pdf_path)
    
    for page_num, page in enumerate(doc):
        drawings = page.get_drawings()
        
        for drawing in drawings:
            color = drawing.get('fill', None)
            rect = drawing.get('rect', None)
            
            if color and rect and isinstance(color, (list, tuple)) and len(color) >= 3:
                r, g, b = color[0], color[1], color[2]
                
                # Check if it's black/dark
                if r <= black_threshold and g <= black_threshold and b <= black_threshold:
                    # rect is a fitz.Rect object with x0, y0, x1, y1
                    boxes.append({
                        'page': page_num,
                        'x0': rect[0],
                        'y0': rect[1],
                        'x1': rect[2],
                        'y1': rect[3],
                        'color': (r, g, b),
                        'width': rect[2] - rect[0],
                        'height': rect[3] - rect[1]
                    })
    
    doc.close()
    return boxes


def get_text_positions(pdf_path):
    """
    Extract character positions from PDF.
    Returns: [(page_num, char, x0, y0, x1, y1), ...]
    """
    chars = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            page_chars = page.chars
            
            for char in page_chars:
                chars.append({
                    'page': page_num,
                    'text': char.get('text', ''),
                    'x0': float(char.get('x0', 0)),
                    'y0': float(char.get('top', 0)),  # pdfplumber uses 'top' not 'y0'
                    'x1': float(char.get('x1', 0)),
                    'y1': float(char.get('bottom', 0))
                })
    
    return chars


def boxes_overlap(box1, box2, threshold=0.5):
    """
    Check if two boxes overlap significantly.
    box1, box2: dict with x0, y0, x1, y1
    threshold: minimum overlap ratio to consider as overlapping
    """
    x0_i = max(box1['x0'], box2['x0'])
    y0_i = max(box1['y0'], box2['y0'])
    x1_i = min(box1['x1'], box2['x1'])
    y1_i = min(box1['y1'], box2['y1'])
    
    # No overlap
    if x0_i >= x1_i or y0_i >= y1_i:
        return False
    
    # Calculate intersection area
    intersection_area = (x1_i - x0_i) * (y1_i - y0_i)
    
    # Calculate char box area
    char_area = (box2['x1'] - box2['x0']) * (box2['y1'] - box2['y0'])
    
    if char_area == 0:
        return False
    
    overlap_ratio = intersection_area / char_area
    return overlap_ratio >= threshold


def test_redaction_overlap(pdf_path):
    """
    Test if black boxes overlap with text positions.
    """
    print(f"\n{'='*80}")
    print(f"TESTING: {pdf_path}")
    print(f"{'='*80}\n")
    
    # Step 1: Get black boxes
    print("Step 1: Finding black boxes...")
    black_boxes = get_black_boxes(pdf_path)
    print(f"  Found {len(black_boxes)} black boxes\n")
    
    if not black_boxes:
        print("  ❌ No black boxes found - cannot be improperly redacted")
        return
    
    # Show first few boxes
    print("  Sample black boxes:")
    for i, box in enumerate(black_boxes[:5]):
        print(f"    Box {i+1}: Page {box['page']}, "
              f"Position ({box['x0']:.1f}, {box['y0']:.1f}) to ({box['x1']:.1f}, {box['y1']:.1f}), "
              f"Size: {box['width']:.1f} x {box['height']:.1f}")
    
    if len(black_boxes) > 5:
        print(f"    ... and {len(black_boxes) - 5} more")
    
    # Step 2: Get text positions
    print(f"\nStep 2: Extracting text positions...")
    text_chars = get_text_positions(pdf_path)
    print(f"  Found {len(text_chars)} characters\n")
    
    if not text_chars:
        print("  ❌ No selectable text found")
        return
    
    # Step 3: Check for overlap
    print("Step 3: Checking for text under black boxes...\n")
    
    overlaps = []
    for box in black_boxes:
        box_overlaps = []
        
        # Check only chars on the same page
        page_chars = [c for c in text_chars if c['page'] == box['page']]
        
        for char in page_chars:
            if boxes_overlap(box, char, threshold=0.3):  # 30% overlap threshold
                box_overlaps.append(char)
        
        if box_overlaps:
            overlaps.append({
                'box': box,
                'chars': box_overlaps
            })
    
    # Results
    print(f"{'='*80}")
    print(f"RESULTS")
    print(f"{'='*80}\n")
    
    print(f"Total black boxes: {len(black_boxes)}")
    print(f"Black boxes with text underneath: {len(overlaps)}")
    print(f"Total characters under black boxes: {sum(len(o['chars']) for o in overlaps)}\n")
    
    if overlaps:
        print("✅ IMPROPERLY REDACTED - Text found under black boxes!\n")
        print("Sample recoverable text:\n")
        
        # Show first few examples
        for i, overlap in enumerate(overlaps[:10]):
            box = overlap['box']
            chars = overlap['chars']
            text = ''.join([c['text'] for c in chars])
            
            print(f"  Redaction Box {i+1} (Page {box['page']}):")
            print(f"    Position: ({box['x0']:.1f}, {box['y0']:.1f}) to ({box['x1']:.1f}, {box['y1']:.1f})")
            print(f"    Hidden text ({len(chars)} chars): '{text}'")
            print()
        
        if len(overlaps) > 10:
            print(f"  ... and {len(overlaps) - 10} more redacted areas with recoverable text\n")
    else:
        print("❌ PROPERLY REDACTED - No text found under black boxes")
        print("   (Text may have been actually removed, or boxes don't overlap text)\n")
    
    print(f"{'='*80}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_box_text_overlap.py <pdf_file>")
        sys.exit(1)
    
    test_redaction_overlap(sys.argv[1])
