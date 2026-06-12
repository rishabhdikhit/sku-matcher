"""
Live SKU -> Sheet matcher  (OCR-heavy build)

Hold a SKU inside the on-screen box. The banner shows
SHEET 1 / SHEET 2 / NOT FOUND in real time. Nothing is saved.

Primary reader : easyocr (reads plain printed text)
Bonus reader   : OpenCV QR + barcode (free, no extra install)

Run:  python sku_match.py
Quit: press q  (or close the window)

SKU list comes from skus.xlsx in this folder, two tabs.
First tab -> "Sheet 1", second tab -> "Sheet 2".
If a tab has a column headed SKU it is used, else the first column.
"""

import os
import sys
import time
import difflib
import threading

import cv2
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))

# Your data. Each entry: (csv_path, label). First file -> "Sheet 1", etc.
SHEETS = [
    (r"C:\Users\Lenovo\Downloads\01.csv", "Sheet 1"),
    (r"C:\Users\Lenovo\Downloads\02.csv", "Sheet 2"),
]
SKU_COL = 1   # 0-based column index holding the SKU code in those CSVs
SKIP_VALUES = {"SIZE", "TOTAL", "COUNT", ""}

# How close an OCR read must be to a real SKU to count as a match.
# 1.0 = exact only. 0.85 tolerates ~1 wrong char in a short code.
FUZZY_CUTOFF = 0.85

# Restrict OCR to the characters SKUs actually use -> faster + more accurate.
ALLOWLIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"

# OCR is slow on big images; cap the scan region's width before recognition.
OCR_MAX_W = 800

# ---- OpenCV native detectors (no extra DLLs) ----
_qr = cv2.QRCodeDetector()
try:
    _bar = cv2.barcode.BarcodeDetector()
    HAVE_BARCODE = True
except Exception:
    HAVE_BARCODE = False

# ---- easyocr (heavy, lazy-loaded) ----
_OCR = None
def get_ocr():
    global _OCR
    if _OCR is not None:
        return _OCR or None
    try:
        import easyocr
        print("  Loading OCR model (first run downloads ~100MB)...")
        _OCR = easyocr.Reader(["en"], gpu=False)
        print("  OCR ready.")
    except Exception as e:
        print(f"  OCR unavailable: {e}")
        _OCR = False
    return _OCR or None


def norm(s):
    return "".join(str(s).split()).upper()


# Fold characters that webcam OCR routinely confuses, so O/0, I/1, S/5 etc.
# all collapse to one canonical form for matching.
_CONFUSE = str.maketrans({
    "O": "0",
    "I": "1", "L": "1",
    "S": "5",
    "B": "8",
    "Z": "2",
    "G": "6",
    "-": "", "_": "", ".": "", "/": "", " ": "",
})
def canon(s):
    return norm(s).translate(_CONFUSE)


_CANON_INDEX = None
def build_canon_index(lookup):
    """canon form -> set of original keys that fold to it."""
    idx = {}
    for k in lookup:
        idx.setdefault(canon(k), set()).add(k)
    return idx


def sheets_to_label(sheets):
    """A set of sheet labels -> one display label."""
    s = sorted(sheets)
    if len(s) == 1:
        return s[0]                       # "Sheet 1" or "Sheet 2"
    return "Both " + " & ".join(x.replace("Sheet ", "") for x in s)  # "Both 1 & 2"


def load_sheets(_=None):
    """Read the CSVs in SHEETS. Return dict: normalized SKU -> set(sheet labels)."""
    lookup = {}
    counts = {}
    for path, label in SHEETS:
        if not os.path.exists(path):
            print(f"\n  ERROR: {path} not found.\n")
            sys.exit(1)
        df = pd.read_csv(path, header=None, dtype=str, keep_default_na=False)
        if SKU_COL >= df.shape[1]:
            print(f"\n  ERROR: {path} has no column index {SKU_COL}.\n")
            sys.exit(1)
        n = 0
        for raw in df[SKU_COL]:
            key = norm(raw)
            if key and key not in SKIP_VALUES:
                lookup.setdefault(key, set()).add(label)
                n += 1
        counts[label] = n
    both = sum(1 for v in lookup.values() if len(v) > 1)
    print(f"  Loaded {len(lookup)} unique SKUs  ("
          + ", ".join(f"{lbl}: {c}" for lbl, c in counts.items())
          + f", in both: {both})")
    return lookup


def _resolve(hits, lookup):
    """hits = set of real SKU keys that a read maps to. Return (label, key)."""
    if len(hits) == 1:
        k = next(iter(hits))
        return sheets_to_label(lookup[k]), k
    # several real SKUs. If they all carry the same sheet membership, it's safe.
    memberships = {frozenset(lookup[k]) for k in hits}
    if len(memberships) == 1:
        k = sorted(hits)[0]
        return sheets_to_label(lookup[k]), k
    return "AMBIGUOUS", "/".join(sorted(hits))


def match_sku(text, lookup):
    """Return (label, matched_key) for an OCR/scan string.
    label is 'Sheet 1'/'Sheet 2'/'Both 1 & 2', 'AMBIGUOUS', or (None, None)."""
    global _CANON_INDEX
    if _CANON_INDEX is None:
        _CANON_INDEX = build_canon_index(lookup)
    key = norm(text)
    if not key:
        return None, None
    # 1) exact
    if key in lookup:
        return sheets_to_label(lookup[key]), key
    if len(key) < 3:
        return None, None
    # 2) confusable-folded exact
    ckey = canon(key)
    hits = _CANON_INDEX.get(ckey)
    if hits:
        return _resolve(hits, lookup)
    # 3) fuzzy on folded forms (tolerate ~1 slip)
    close = difflib.get_close_matches(ckey, _CANON_INDEX.keys(), n=1, cutoff=FUZZY_CUTOFF)
    if close:
        return _resolve(_CANON_INDEX[close[0]], lookup)
    return None, None


def scan_codes(frame):
    """OpenCV QR + barcode. Returns list of decoded strings."""
    out = []
    try:
        data, pts, _ = _qr.detectAndDecode(frame)
        if data:
            out.append(data)
    except Exception:
        pass
    if HAVE_BARCODE:
        try:
            ok, infos, _types, _pts = _bar.detectAndDecodeMulti(frame)
            if ok and infos:
                out.extend([s for s in infos if s])
        except Exception:
            pass
    return out


def open_source(source):
    """source: int-like string -> local webcam index; anything else -> URL/path."""
    if str(source).isdigit():
        cap = cv2.VideoCapture(int(source), cv2.CAP_DSHOW)  # local cam (DSHOW = fast)
        what = f"webcam index {source}"
    else:
        cap = cv2.VideoCapture(str(source))                 # phone MJPEG/RTSP/HTTP URL
        what = source
    return cap, what


def roi_box(w, h):
    """Center scan box coordinates."""
    return int(w * 0.15), int(h * 0.30), int(w * 0.85), int(h * 0.70)


def result_banner(label, hit, candidates):
    """Map a match result to (banner_text, BGR_color)."""
    shown = hit or norm(candidates[0])
    if label == "Sheet 1":
        return f"SHEET 1   [{shown}]", (0, 200, 0)
    if label == "Sheet 2":
        return f"SHEET 2   [{shown}]", (230, 130, 0)
    if label and label.startswith("Both"):
        return f"BOTH 1 & 2   [{shown}]", (230, 230, 230)
    if label == "AMBIGUOUS":
        return f"AMBIGUOUS  [{shown}]", (0, 215, 255)
    if label:
        return f"{label}   [{shown}]", (0, 200, 0)
    return f"NOT FOUND  [{norm(candidates[0])}]", (0, 0, 230)


def main(source="0"):
    print("\nSKU -> Sheet matcher  (OCR-heavy, threaded)\n"
          "-------------------------------------------")
    lookup = load_sheets()
    reader = get_ocr()  # warm the model before threads start

    cap, what = open_source(source)
    print(f"  Opening {what} ... (press q to quit)\n")
    if not cap.isOpened():
        print(f"  ERROR: could not open {what}.")
        print("  - local cam: try --source 1 (or 2)")
        print("  - phone: check the URL and that phone+laptop are on the SAME WiFi\n")
        sys.exit(1)
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # don't queue stale frames
    except Exception:
        pass

    state = {"frame": None,
             "result": ("Show a SKU in the box", (200, 200, 200), 0.0),
             "running": True}
    lock = threading.Lock()

    def capture_loop():
        # Always keep only the freshest frame -> no latency build-up.
        while state["running"]:
            ok, f = cap.read()
            if not ok:
                time.sleep(0.01)
                continue
            with lock:
                state["frame"] = f

    def ocr_loop():
        # Heavy work lives here, off the display thread.
        while state["running"]:
            with lock:
                f = state["frame"]
                f = f.copy() if f is not None else None
            if f is None:
                time.sleep(0.02)
                continue
            h, w = f.shape[:2]
            bx0, by0, bx1, by1 = roi_box(w, h)
            roi = f[by0:by1, bx0:bx1]

            candidates = scan_codes(roi)                  # QR/barcode (cheap)
            if not candidates and reader is not None:
                ocr_img = roi
                if roi.shape[1] > OCR_MAX_W:              # shrink for speed
                    s = OCR_MAX_W / roi.shape[1]
                    ocr_img = cv2.resize(roi, None, fx=s, fy=s)
                try:
                    for (_b, txt, conf) in reader.readtext(ocr_img, allowlist=ALLOWLIST):
                        if conf > 0.35:
                            candidates.append(txt)
                except Exception:
                    pass

            if candidates:
                label, hit = None, None
                for c in candidates:
                    label, hit = match_sku(c, lookup)
                    if label:
                        break
                text, color = result_banner(label, hit, candidates)
                with lock:
                    state["result"] = (text, color, time.time())
            else:
                time.sleep(0.01)

    threading.Thread(target=capture_loop, daemon=True).start()
    threading.Thread(target=ocr_loop, daemon=True).start()

    win = "SKU -> Sheet"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)  # resizable; image scales to fit
    sized = False
    while True:
        with lock:
            frame = state["frame"]
            frame = frame.copy() if frame is not None else None
            text, color, seen = state["result"]
        if frame is None:
            if (cv2.waitKey(30) & 0xFF) == ord("q"):
                break
            continue

        h, w = frame.shape[:2]
        if not sized:
            # fit the window inside ~960x600 on first frame, keep aspect
            scale = min(960.0 / w, 600.0 / h, 1.0)
            cv2.resizeWindow(win, max(int(w * scale), 320), max(int(h * scale), 240))
            sized = True
        bx0, by0, bx1, by1 = roi_box(w, h)
        if seen and time.time() - seen > 1.3:
            text, color = "Show a SKU in the box", (200, 200, 200)

        cv2.rectangle(frame, (bx0, by0), (bx1, by1), (90, 90, 90), 2)
        cv2.rectangle(frame, (0, 0), (w, 70), (0, 0, 0), -1)
        cv2.putText(frame, text, (15, 48), cv2.FONT_HERSHEY_SIMPLEX,
                    1.0, color, 3, cv2.LINE_AA)
        cv2.putText(frame, "q = quit", (w - 130, h - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1, cv2.LINE_AA)

        cv2.imshow(win, frame)
        if (cv2.waitKey(1) & 0xFF) == ord("q"):
            break
        if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
            break

    state["running"] = False
    time.sleep(0.15)
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    src = "0"
    for i, a in enumerate(sys.argv):
        if a in ("--source", "-s") and i + 1 < len(sys.argv):
            src = sys.argv[i + 1]
    main(src)
