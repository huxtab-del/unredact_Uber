import fitz  # PyMuPDF
import pdfplumber
import sys

def analyze_pdf_structure(pdf_path):
    """Deep analysis of PDF structure to understand redaction method."""
    
    print(f"\n{'='*70}")
    print(f"ANALYZING: {pdf_path}")
    print(f"{'='*70}\n")
    
    # PyMuPDF analysis
    print("=== PyMuPDF Analysis ===")
    doc = fitz.open(pdf_path)
    
    for page_num, page in enumerate(doc):
        print(f"\nPage {page_num + 1}:")
        print(f"  Size: {page.rect.width} x {page.rect.height}")
        
        # Check text
        text = page.get_text()
        print(f"  Text length: {len(text)} chars")
        if text:
            print(f"  Text sample: {text[:100]}...")
        
        # Check drawings
        drawings = page.get_drawings()
        print(f"  Drawings: {len(drawings)}")
        if drawings:
            for i, d in enumerate(drawings[:3]):
                print(f"    Drawing {i}: type={d.get('type')}, fill={d.get('fill')}, rect={d.get('rect')}")
        
        # Check images
        images = page.get_images()
        print(f"  Images: {len(images)}")
        
        # Check annotations (might be redactions)
        annots = page.annots()
        annot_list = list(annots) if annots else []
        print(f"  Annotations: {len(annot_list)}")
        if annot_list:
            for annot in annot_list[:3]:
                print(f"    Annotation: type={annot.type[1]}, rect={annot.rect}")
        
        # Check if it's a scanned image
        blocks = page.get_text("dict")["blocks"]
        image_blocks = [b for b in blocks if b.get("type") == 1]
        text_blocks = [b for b in blocks if b.get("type") == 0]
        print(f"  Image blocks: {len(image_blocks)}, Text blocks: {len(text_blocks)}")
        
        if page_num >= 2:  # Just check first 3 pages
            break
    
    doc.close()
    
    # pdfplumber analysis
    print(f"\n=== pdfplumber Analysis ===")
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            print(f"\nPage {page_num + 1}:")
            
            # Extract text
            text = page.extract_text()
            print(f"  Extractable text: {len(text) if text else 0} chars")
            
            # Get words
            words = page.extract_words()
            print(f"  Words: {len(words)}")
            
            # Get characters
            chars = page.chars
            print(f"  Characters: {len(chars)}")
            
            # Check for rectangles
            rects = page.rects
            print(f"  Rectangles: {len(rects)}")
            if rects:
                for rect in rects[:3]:
                    print(f"    Rect: {rect}")
            
            # Check for curves/lines
            curves = page.curves
            print(f"  Curves: {len(curves)}")
            
            if page_num >= 2:
                break
    
    print(f"\n{'='*70}\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_pdf_structure.py <pdf_file>")
        sys.exit(1)
    
    analyze_pdf_structure(sys.argv[1])
