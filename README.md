# SKU → Sheet matcher

Hold a SKU to a camera; a window shows which sheet(s) it belongs to — live.
Manage the sheets from a browser dashboard (reachable from your phone too).
Nothing is saved server-side beyond the CSVs you upload.

## Install
```
pip install -r requirements.txt
```

## 1. Dashboard — manage sheets
```
python dashboard.py
```
- Opens on the laptop at `http://127.0.0.1:5000`.
- Open it from a phone (Android or iPhone) on the **same WiFi** at the
  `http://<laptop-ip>:5000` URL it prints.
- Add up to several CSV sheets (label + file + which 0-based column holds the
  SKU). Download or remove sheets. Test a SKU. Enter your **phone camera IP**
  and hit **Start phone scan**, or **Use laptop camera**.

Sheets live in `sheets.json` + `data/`; the phone IP is remembered in
`settings.json`. None of those are committed to git.

## 2. Scanner — the camera window
Launched from the dashboard, or directly:
```
python sku_match.py                                   # laptop webcam
python sku_match.py --source 1                        # another local cam
python sku_match.py --source http://PHONE_IP:8080/video   # phone stream
```
Banner shows the sheet label (green/orange/… per sheet), `A + B` when a SKU is
in several sheets, `AMBIGUOUS`, or `NOT FOUND`. Press **q** to quit.

## Phone as the camera
Both devices on the same WiFi.
- **Android:** install *IP Webcam* → Start server → it shows `http://IP:8080`.
- **iPhone:** install *IP Camera Lite* (or similar) → note its stream address.
Put that IP into the dashboard's **Phone camera IP** box. ~720p is the sweet
spot (the scanner caps its scan region at 800px internally).

## How matching works
- Reads the SKU via OpenCV QR/barcode (instant) or easyocr text OCR (CPU).
- Capture + OCR run on separate threads, so the video stays smooth.
- OCR-confusable characters (O/0, I/1, S/5, B/8, Z/2, G/6) are folded, plus a
  one-slip fuzzy fallback. Reads that map to >1 different SKU show AMBIGUOUS.

## Files
`dashboard.py` web UI · `sku_match.py` scanner · `sheetstore.py` shared data +
matching · `test_match.py` / `test_dashboard.py` offline checks.

## Accuracy note
Webcam OCR of long text codes is imperfect. Barcodes/QR read near-perfectly —
prefer them where you can.
