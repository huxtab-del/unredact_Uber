import os
import argparse
import pdfplumber
import fitz  # PyMuPDF
from multiprocessing import Pool, cpu_count
from tqdm import tqdm
import time
import json
from pathlib import Path


def test_text_selectability(pdf_path):
    """
    Test if a PDF has selectable text that might be under redactions.
    This checks if there's text in the PDF that can be extracted but might be visually hidden.
    """
    result = {
        'path': pdf_path,
        'filename': os.path.basename(pdf_path),
        'total_chars': 0,
        'has_text_layer': False,
        'has_black_elements': False,
        'text_sample': '',
        'should_process': False,
        'error': None
    }
    
    try:
        # Method 1: Check if PDF has selectable text using pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            all_text = ''
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    all_text += page_text
            
            result['total_chars'] = len(all_text)
            result['has_text_layer'] = len(all_text) > 0
            result['text_sample'] = all_text[:200] if all_text else ''
        
        # Method 2: Check for black filled areas using PyMuPDF
        doc = fitz.open(pdf_path)
        has_black = False
        
        for page in doc:
            # Check for black rectangles in drawings
            drawings = page.get_drawings()
            for drawing in drawings:
                color = drawing.get('fill', None)
                if color and isinstance(color, (list, tuple)) and len(color) >= 3:
                    r, g, b = color[0], color[1], color[2]
                    if r <= 0.2 and g <= 0.2 and b <= 0.2:  # Dark/black
                        has_black = True
                        break
            
            if has_black:
                break
        
        doc.close()
        result['has_black_elements'] = has_black
        
        # Should process if it has both text layer AND black elements
        # This suggests potential redactions with recoverable text
        result['should_process'] = result['has_text_layer'] and result['has_black_elements']
        
    except Exception as e:
        result['error'] = str(e)
    
    return result


def scan_directory_smart(directory, recursive=True, workers=None, max_files=None):
    """
    Scan directory for PDFs that might have selectable redacted text.
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
                    if max_files and len(pdf_files) >= max_files:
                        break
            if max_files and len(pdf_files) >= max_files:
                break
    else:
        pdf_files = [
            os.path.join(directory, f) 
            for f in os.listdir(directory) 
            if f.lower().endswith('.pdf')
        ]
        if max_files:
            pdf_files = pdf_files[:max_files]
    
    if not pdf_files:
        print(f"No PDF files found in {directory}")
        return []
    
    print(f"\nFound {len(pdf_files)} PDF files")
    print(f"Scanning using {workers} workers...\n")
    
    # Analyze PDFs in parallel
    with Pool(processes=workers) as pool:
        results = list(tqdm(
            pool.imap(test_text_selectability, pdf_files),
            total=len(pdf_files),
            desc="Scanning PDFs",
            unit="file"
        ))
    
    return results


def extract_text_to_file(pdf_path, output_txt):
    """
    Extract all selectable text from a PDF to a text file.
    This is useful to see what text can actually be copied from a "redacted" PDF.
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            all_text = []
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    all_text.append(f"{'='*60}\nPAGE {i+1}\n{'='*60}\n")
                    all_text.append(page_text)
                    all_text.append("\n\n")
        
        with open(output_txt, 'w', encoding='utf-8') as f:
            f.write(''.join(all_text))
        
        return True
    except Exception as e:
        print(f"Error extracting text from {pdf_path}: {e}")
        return False


def main():
    ap = argparse.ArgumentParser(
        description="Find PDFs with selectable text under potential redactions"
    )
    ap.add_argument("input", help="PDF file or directory to scan")
    ap.add_argument("-o", "--output", default=None,
                    help="Output directory for extracted text files")
    ap.add_argument("--extract-text", action="store_true",
                    help="Extract all selectable text to .txt files")
    ap.add_argument("--recursive", "-r", action="store_true", default=True,
                    help="Recursively scan subdirectories")
    ap.add_argument("--workers", type=int, default=None,
                    help=f"Number of parallel workers")
    ap.add_argument("--report", default=None,
                    help="Save analysis report to JSON file")
    ap.add_argument("--max-files", type=int, default=None,
                    help="Maximum number of files to scan (for testing)")
    ap.add_argument("--min-chars", type=int, default=100,
                    help="Minimum characters to consider PDF as having text")
    args = ap.parse_args()
    
    start_time = time.time()
    
    # Determine if input is file or directory
    if os.path.isfile(args.input):
        print(f"Analyzing single file: {args.input}\n")
        results = [test_text_selectability(args.input)]
    elif os.path.isdir(args.input):
        results = scan_directory_smart(
            args.input,
            recursive=args.recursive,
            workers=args.workers,
            max_files=args.max_files
        )
    else:
        print(f"❌ Input not found: {args.input}")
        return
    
    # Filter results
    has_text = [r for r in results if r['total_chars'] >= args.min_chars]
    has_black = [r for r in results if r['has_black_elements']]
    candidates = [r for r in results if r['should_process']]
    
    # Print summary
    print(f"\n{'='*70}")
    print(f"SCAN RESULTS SUMMARY")
    print(f"{'='*70}")
    print(f"Total PDFs scanned: {len(results)}")
    print(f"PDFs with text layer ({args.min_chars}+ chars): {len(has_text)}")
    print(f"PDFs with black elements: {len(has_black)}")
    print(f"PDFs with BOTH (candidates): {len(candidates)}")
    print(f"{'='*70}\n")
    
    if candidates:
        print(f"📋 Candidate PDFs (have text + black elements):\n")
        for r in candidates[:20]:  # Show first 20
            print(f"   • {r['filename']}")
            print(f"     Characters: {r['total_chars']:,}")
            print(f"     Sample: {r['text_sample'][:80]}...")
            print()
        
        if len(candidates) > 20:
            print(f"   ... and {len(candidates) - 20} more\n")
    
    # Save report if requested
    if args.report:
        report = {
            'total_files': len(results),
            'files_with_text': len(has_text),
            'files_with_black_elements': len(has_black),
            'candidate_files': len(candidates),
            'min_chars_threshold': args.min_chars,
            'files': results
        }
        
        with open(args.report, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"📄 Report saved to: {args.report}\n")
    
    # Extract text if requested
    if args.extract_text and candidates:
        if args.output:
            os.makedirs(args.output, exist_ok=True)
        else:
            args.output = "./extracted_text"
            os.makedirs(args.output, exist_ok=True)
        
        print(f"\n{'='*70}")
        print(f"EXTRACTING SELECTABLE TEXT")
        print(f"{'='*70}\n")
        
        for r in tqdm(candidates, desc="Extracting text", unit="file"):
            output_txt = os.path.join(
                args.output,
                f"{Path(r['filename']).stem}_extracted.txt"
            )
            extract_text_to_file(r['path'], output_txt)
        
        print(f"\n✅ Extracted text saved to: {args.output}")
    
    total_time = time.time() - start_time
    print(f"\n⏱️  Total execution time: {total_time:.2f}s")


if __name__ == "__main__":
    main()
