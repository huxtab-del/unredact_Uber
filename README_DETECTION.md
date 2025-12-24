# 🔍 Intelligent Redaction Detection & Recovery System

## Overview

This tool intelligently scans PDFs to detect redaction boxes and identify recoverable text underneath, processing **only** those PDFs that have actual recoverable redacted content. Perfect for efficiently processing large document sets like the Epstein files.

## 🎯 Key Features

### **1. Smart Detection**
- ✅ Detects black rectangles/boxes (common redaction method)
- ✅ Identifies text positioned under redaction boxes
- ✅ Filters out PDFs without redactions or recoverable text
- ✅ **Skips clean PDFs automatically** - saves massive processing time

### **2. Three-Stage Analysis**
1. **Redaction Box Detection** - Finds black rectangles that may be redactions
2. **Text Recovery Check** - Tests if text exists under those boxes
3. **Smart Filtering** - Only processes PDFs with recoverable content

### **3. Multiple Output Modes**
- **Highlight Mode** (default): Highlights redacted areas in yellow
- **Side-by-Side Mode**: Shows original vs extracted text
- **Overlay White Mode**: White text overlay on redactions

### **4. Parallel Processing**
- Multi-core scanning for fast directory analysis
- Efficient batch processing
- Progress tracking for large datasets

---

## 🚀 Usage Examples

### **Single File Analysis**

```bash
# Analyze single PDF
python detect_and_recover_redactions.py document.pdf

# Scan only (no processing)
python detect_and_recover_redactions.py document.pdf --scan-only

# Process with highlighting
python detect_and_recover_redactions.py document.pdf -o ./output/
```

### **Directory Scanning**

```bash
# Scan entire directory recursively
python detect_and_recover_redactions.py "C:\Documents\Epstein\" -r

# Scan and create analysis report
python detect_and_recover_redactions.py "C:\Documents\Epstein\" --report analysis.json

# Scan only (don't process files yet)
python detect_and_recover_redactions.py "C:\Documents\Epstein\" --scan-only
```

### **Batch Processing**

```bash
# Process all PDFs with recoverable redactions in a directory
python detect_and_recover_redactions.py "C:\Documents\Dataset 8\" -o ./recovered/ --mode highlight

# Side-by-side comparison mode
python detect_and_recover_redactions.py "C:\Documents\Dataset 8\" -o ./output/ --mode side_by_side

# White overlay mode
python detect_and_recover_redactions.py "C:\Documents\Dataset 8\" -o ./output/ --mode overlay_white

# Use more workers for faster processing
python detect_and_recover_redactions.py "C:\Documents\Dataset 8\" -o ./output/ --workers 12
```

---

## 📊 Example Output

```
Found 1243 PDF files
Analyzing for redactions using 11 workers...

Scanning PDFs: 100%|████████████| 1243/1243 [05:23<00:00, 3.84file/s]

============================================================
SCAN RESULTS SUMMARY
============================================================
Total PDFs scanned: 1243
PDFs with redaction boxes: 89
PDFs with recoverable text: 34
PDFs to process: 34

📋 Files with recoverable redacted text:
   • EFTA00015277.pdf (127 chars)
   • EFTA00015834.pdf (89 chars)
   • EFTA00016192.pdf (203 chars)
   ...

✅ Found 34 PDF(s) with recoverable redacted text
📊 Summary:
   - Total scanned: 1243
   - With redaction boxes: 89
   - With recoverable text: 34
   - Will process: 34

[1/34] Processing: EFTA00015277.pdf
   Redacted characters found: 127
   ✓ Created highlighted version: ./output/EFTA00015277_unredacted.pdf
...
```

---

## 🎯 Command-Line Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `input` | str | required | PDF file or directory to scan |
| `-o, --output` | str | same as input | Output directory for processed PDFs |
| `--mode` | choice | `highlight` | Output mode: `highlight`, `side_by_side`, or `overlay_white` |
| `--scan-only` | flag | false | Only scan and report, don't process |
| `-r, --recursive` | flag | true | Recursively scan subdirectories |
| `--workers` | int | CPU-1 | Number of parallel workers |
| `--report` | str | none | Save analysis report to JSON file |

---

## 🔬 How Detection Works

### **Step 1: Redaction Box Detection**
Scans PDF vector graphics for:
- Black filled rectangles (RGB ≤ 0.15)
- Solid color image blocks
- Common redaction patterns

### **Step 2: Text Position Analysis**
- Extracts character-level positions using `pdfplumber`
- Calculates bounding boxes for each character
- Checks for overlap with detected redaction boxes

### **Step 3: Smart Filtering**
Only processes PDFs where:
```
has_redaction_boxes = True
AND
has_recoverable_text = True
```

This **skips** PDFs that:
- Have no redactions at all
- Have proper redactions (text actually removed)
- Are scanned images with no text layer

---

## 📋 Analysis Report (JSON)

When using `--report`, creates a detailed JSON report:

```json
{
  "total_files": 1243,
  "files_with_redaction_boxes": 89,
  "files_with_recoverable_text": 34,
  "files_to_process": 34,
  "files": [
    {
      "path": "C:\\Docs\\file.pdf",
      "filename": "file.pdf",
      "has_redaction_boxes": true,
      "has_recoverable_text": true,
      "redaction_box_count": 5,
      "redacted_char_count": 127,
      "should_process": true,
      "error": null
    }
  ]
}
```

---

## 🎨 Output Modes Explained

### **1. Highlight Mode (Default)**
- Fastest processing
- Adds yellow transparent highlights over redacted areas
- Keeps original PDF intact
- Best for quick review

### **2. Side-by-Side Mode**
- Double-width pages
- Left: Original document
- Right: Extracted text positioned to match
- Best for detailed comparison

### **3. Overlay White Mode**
- White text overlaid on original
- Text becomes visible on black redactions
- Best for demonstrating the issue

---

## 💡 Use Cases

### **For Large Datasets (e.g., Epstein Documents)**

```bash
# Step 1: Scan entire dataset (fast, no processing)
python detect_and_recover_redactions.py \
  "C:\Users\mackp\Documents\Ep\" \
  --scan-only \
  --report epstein_analysis.json

# Step 2: Review the report to see what was found

# Step 3: Process only files with recoverable text
python detect_and_recover_redactions.py \
  "C:\Users\mackp\Documents\Ep\" \
  -o "C:\Recovered\" \
  --mode highlight \
  --workers 12
```

### **For Quick Single File Check**

```bash
# Check if a specific document has recoverable redactions
python detect_and_recover_redactions.py document.pdf --scan-only
```

---

## ⚡ Performance

| Task | Speed (12 cores) | Notes |
|------|------------------|-------|
| Scan 1000 PDFs | ~3-5 minutes | Detection only |
| Process 1 PDF (3 pages) | ~1-2 seconds | Highlight mode |
| Process 100 recoverable PDFs | ~5-10 minutes | Full processing |

**Efficiency Gain:**
- Without filtering: Process all 1000 PDFs → ~2 hours
- With filtering: Process only 34 PDFs → ~5 minutes
- **Time saved: 96%** ⚡

---

## 🛠️ Technical Details

### **Redaction Detection Algorithm**

1. **Vector Graphics Analysis**
   - Scans PDF drawing commands
   - Identifies filled paths (type 'f')
   - Filters by color (black threshold)

2. **Overlap Calculation**
   ```python
   overlap_ratio = intersection_area / char_area
   if overlap_ratio >= 0.5:  # 50% threshold
       # Character is considered redacted
   ```

3. **Character-Level Precision**
   - Uses character bounding boxes, not words
   - More accurate than line-based detection
   - Catches partial redactions

---

## 🔒 Legal & Ethical Use

This tool is designed for:
- ✅ Document analysis and review
- ✅ Compliance auditing
- ✅ Identifying improper redactions
- ✅ Quality assurance of redaction processes

**Important:**
- Only works on improperly redacted PDFs
- Does NOT bypass encryption or security
- Use responsibly and legally
- Respect privacy and confidentiality requirements

---

## 🆚 Comparison: Original vs Detection System

| Feature | Original Script | Detection System |
|---------|----------------|------------------|
| Processing | All PDFs | Only PDFs with recoverable text |
| Speed (1000 PDFs) | ~2 hours | ~10 minutes (if 3% have issues) |
| False Positives | High | Very Low |
| Efficiency | Baseline | **96% time savings** |
| Pre-scanning | No | Yes |
| Reporting | No | JSON report available |

---

## 📌 Tips & Best Practices

1. **Always scan first** with `--scan-only` on large datasets
2. **Review the JSON report** before processing
3. **Use highlight mode** for quick initial review
4. **Use side-by-side mode** for detailed analysis
5. **Adjust `--workers`** based on your CPU cores
6. **Save reports** for documentation and auditing

---

## 🐛 Troubleshooting

**"No PDFs found with recoverable text"**
- This is good! It means redactions are proper
- Or PDFs are scanned images without text layers

**"Too many files detected"**
- Check the JSON report for false positives
- Adjust black_threshold in code if needed

**Slow scanning**
- Increase `--workers`
- Use SSD storage
- Process smaller batches

---

## 🚀 Next Steps

After scanning the Epstein dataset:

1. Review `--report` JSON to see findings
2. Process high-priority files first
3. Generate comprehensive reports
4. Document any discovered redaction failures
5. Use for compliance and quality auditing
