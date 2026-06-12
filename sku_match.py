"""
Live SKU -> Sheet scanner  (OCR-heavy, threaded)

Hold a SKU to the camera; the window shows which sheet(s) it belongs to,
live. Sheets are configured in the dashboard (dashboard.py) and read from
sheets.json — this scanner supports any number of sheets.

Run:  python sku_match.py                 (built-in webcam)
      python sku_match.py --source 1       (other local cam)
      python sku_match.py --source http://PHONE_IP:8080/video   (phone)
Quit: press q  (or close the window)
"""

import os
import sys
import time
import threading

import cv2

import sheetstore as ss
from sheetstore import norm, match_sku

# Per-sheet colors (BGR). Assigned in config order; extra sheets reuse the palette.
PALETTE = [(0, 200, 0), (230, 130, 0), (0, 170, 255), (200, 0, 200),
           (180, 180, 0), (120, 90, 230)]
MULTI_COLOR = (240, 240, 240)     # SKU in more than one sheet
AMBIG_COLOR = (0, 215, 255)
NOTFOUND_COLOR = (0, 0, 230)
IDLE_COLOR = (200, 200, 200)

ALLOWLIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"
OCR_MAX_W = 800
LOG_COOLDOWN = 3.0   # seconds; don't re-log the same SKU held in frame

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


def scan_codes(frame):
    """OpenCV QR + barcode. Returns list of decoded strings."""
    out = []
    try:
        data, _pts, _ = _qr.detectAndDecode(frame)
        if data:
            out.append(data)
    except Exception:
        pass
    if HAVE_BARCODE:
        try:
            ok, infos, _t, _p = _bar.detectAndDecodeMulti(frame)
            if ok and infos:
                out.extend([s for s in infos if s])
        except Exception:
            pass
    return out


def open_source(source):
    if str(source).isdigit():
        cap = cv2.VideoCapture(int(source), cv2.CAP_DSHOW)
        return cap, f"webcam index {source}"
    cap = cv2.VideoCapture(str(source))
    return cap, str(source)


def roi_box(w, h):
    return int(w * 0.15), int(h * 0.30), int(w * 0.85), int(h * 0.70)


def result_banner(label, hit, candidates, colors):
    shown = hit or norm(candidates[0])
    if not label:
        return f"NOT FOUND  [{norm(candidates[0])}]", NOTFOUND_COLOR
    if label == "AMBIGUOUS":
        return f"AMBIGUOUS  [{shown}]", AMBIG_COLOR
    color = colors.get(label, MULTI_COLOR)   # multi-sheet labels aren't in the map
    return f"{label.upper()}   [{shown}]", color


def main(source="0"):
    print("\nSKU -> Sheet scanner  (threaded)\n--------------------------------")
    cfg = ss.ensure_config()
    if not cfg:
        print("  No sheets configured yet.")
        print("  Start the dashboard (python dashboard.py) and add CSV sheets first.\n")
        sys.exit(1)
    lookup, counts = ss.build_lookup(cfg)
    canon_index = ss.build_canon_index(lookup)
    colors = {s["label"]: PALETTE[i % len(PALETTE)] for i, s in enumerate(cfg)}
    both = sum(1 for v in lookup.values() if len(v) > 1)
    print(f"  {len(lookup)} unique SKUs across {len(cfg)} sheets "
          f"({', '.join(f'{k}:{v}' for k, v in counts.items())}; in >1 sheet: {both})")

    reader = get_ocr()
    cap, what = open_source(source)
    print(f"  Opening {what} ... (press q to quit)\n")
    if not cap.isOpened():
        print(f"  ERROR: could not open {what}.")
        print("  - local cam: try --source 1 (or 2)")
        print("  - phone: check the URL and that phone+laptop are on the SAME WiFi\n")
        sys.exit(1)
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass

    state = {"frame": None,
             "result": ("Show a SKU in the box", IDLE_COLOR, 0.0),
             "running": True}
    lock = threading.Lock()
    last_log = {}   # sku -> last time we wrote it to history

    def capture_loop():
        while state["running"]:
            ok, f = cap.read()
            if not ok:
                time.sleep(0.01)
                continue
            with lock:
                state["frame"] = f

    def ocr_loop():
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

            candidates = scan_codes(roi)
            if not candidates and reader is not None:
                ocr_img = roi
                if roi.shape[1] > OCR_MAX_W:
                    sc = OCR_MAX_W / roi.shape[1]
                    ocr_img = cv2.resize(roi, None, fx=sc, fy=sc)
                try:
                    for (_b, txt, conf) in reader.readtext(ocr_img, allowlist=ALLOWLIST):
                        if conf > 0.35:
                            candidates.append(txt)
                except Exception:
                    pass

            if candidates:
                label, hit = None, None
                for c in candidates:
                    label, hit = match_sku(c, lookup, canon_index)
                    if label:
                        break
                text, color = result_banner(label, hit, candidates, colors)
                with lock:
                    state["result"] = (text, color, time.time())
                # log confirmed matches (skip AMBIGUOUS / NOT FOUND noise)
                if label and label != "AMBIGUOUS":
                    k = hit or norm(candidates[0])
                    nowt = time.time()
                    if nowt - last_log.get(k, 0) > LOG_COOLDOWN:
                        last_log[k] = nowt
                        ss.append_scan(k, label, source)
            else:
                time.sleep(0.01)

    threading.Thread(target=capture_loop, daemon=True).start()
    threading.Thread(target=ocr_loop, daemon=True).start()

    win = "SKU -> Sheet"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
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
            scale = min(960.0 / w, 600.0 / h, 1.0)
            cv2.resizeWindow(win, max(int(w * scale), 320), max(int(h * scale), 240))
            sized = True
        bx0, by0, bx1, by1 = roi_box(w, h)
        if seen and time.time() - seen > 1.3:
            text, color = "Show a SKU in the box", IDLE_COLOR

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
