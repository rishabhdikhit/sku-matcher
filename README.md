# Live SKU → Sheet matcher

Hold a SKU in front of the webcam → the window shows **SHEET 1 / SHEET 2 /
NOT FOUND / AMBIGUOUS** in real time. Nothing is saved.

## Run
```
python C:\Users\Lenovo\sku-matcher\sku_match.py
```
Press **q** (or close the window) to quit.

## Your data
Replace **skus.xlsx** in this folder with your real file:
- Two tabs. First tab → "Sheet 1", second tab → "Sheet 2".
- One SKU per row. A column headed `SKU` is used if present, else column 1.

`make_sample.py` regenerates the demo file. `test_match.py` checks the
matching logic without a camera.

## How it reads
- **Primary:** easyocr — reads plain printed text (first run downloads ~100 MB).
- **Bonus:** OpenCV QR + barcode (free, instant, far more accurate).
- Hold the SKU inside the on-screen box. Confusable characters (O/0, I/1,
  S/5, B/8...) are auto-folded. If a read maps to two different SKUs on
  different sheets, it shows **AMBIGUOUS** instead of guessing.

## Accuracy note
Webcam OCR of small text is error-prone. For reliable inventory use, prefer
SKUs with a **barcode/QR** — those read near-perfectly via the bonus path.
