"""
Shared data layer for the SKU matcher.

- sheets.json   : list of {id, label, file, col} describing each source sheet
- data/         : the uploaded CSV files
Both the dashboard (dashboard.py) and the scanner (sku_match.py) import this,
so they always agree on the sheets and the matching rules.
"""

import os
import re
import csv
import json
import shutil
import difflib
import datetime
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(HERE, "sheets.json")
SETTINGS_FILE = os.path.join(HERE, "settings.json")
HISTORY_FILE = os.path.join(HERE, "history.csv")
DATA_DIR = os.path.join(HERE, "data")
HISTORY_HEADER = ["time", "sku", "sheet", "source"]
_hist_lock = threading.Lock()

FUZZY_CUTOFF = 0.85                       # 1.0 = exact only; 0.85 tolerates ~1 slip
SKIP_VALUES = {"SIZE", "TOTAL", "COUNT", ""}

# If there is no config yet, seed from the original two CSVs (if present).
_SEED = [
    (r"C:\Users\Lenovo\Downloads\01.csv", "Sheet 1", 1),
    (r"C:\Users\Lenovo\Downloads\02.csv", "Sheet 2", 1),
]


# ---------- normalization / OCR-confusable folding ----------
def norm(s):
    return "".join(str(s).split()).upper()


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


# ---------- config CRUD ----------
def load_config():
    if not os.path.exists(CONFIG_FILE):
        return []
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def _next_id(cfg):
    return (max((s["id"] for s in cfg), default=0)) + 1


# ---------- small key/value settings (remembers the phone IP, etc.) ----------
def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def get_setting(key, default=""):
    return load_settings().get(key, default)


def set_setting(key, value):
    s = load_settings()
    s[key] = value
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)


# ---------- scan history ----------
def append_scan(sku, sheet, source=""):
    new = not os.path.exists(HISTORY_FILE)
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _hist_lock:
        with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(HISTORY_HEADER)
            w.writerow([ts, sku, sheet, source])


def read_history():
    rows = []
    if not os.path.exists(HISTORY_FILE):
        return rows
    with _hist_lock:
        with open(HISTORY_FILE, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rows.append(row)
    return rows


def clear_history():
    with _hist_lock:
        try:
            os.remove(HISTORY_FILE)
        except OSError:
            pass


def ensure_config():
    """Create data/ and seed sheets.json from the original CSVs the first time."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        cfg = []
        for path, label, col in _SEED:
            if os.path.exists(path):
                fname = unique_name(label)
                shutil.copyfile(path, os.path.join(DATA_DIR, fname))
                cfg.append({"id": _next_id(cfg), "label": label, "file": fname, "col": col})
        save_config(cfg)
    return load_config()


def unique_name(label):
    """A safe, unique data/ filename derived from a label."""
    base = re.sub(r"[^a-z0-9]+", "_", str(label).lower()).strip("_") or "sheet"
    name = f"{base}.csv"
    i = 2
    while os.path.exists(os.path.join(DATA_DIR, name)):
        name = f"{base}_{i}.csv"
        i += 1
    return name


def add_sheet(label, fname, col=1):
    cfg = load_config()
    cfg.append({"id": _next_id(cfg), "label": label, "file": fname, "col": int(col)})
    save_config(cfg)


def get_sheet(sid):
    for s in load_config():
        if s["id"] == sid:
            return s
    return None


def remove_sheet(sid):
    cfg = load_config()
    keep = []
    for s in cfg:
        if s["id"] == sid:
            try:
                os.remove(os.path.join(DATA_DIR, s["file"]))
            except OSError:
                pass
        else:
            keep.append(s)
    save_config(keep)


# ---------- reading SKUs + building the lookup ----------
def read_skus(path, col):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.reader(f):
            if col < len(row):
                v = norm(row[col])
                if v and v not in SKIP_VALUES:
                    out.append(v)
    return out


def build_lookup(cfg=None):
    """Return (lookup, counts): lookup maps SKU -> set(labels); counts per label."""
    if cfg is None:
        cfg = load_config()
    lookup, counts = {}, {}
    for s in cfg:
        path = os.path.join(DATA_DIR, s["file"])
        n = 0
        for key in read_skus(path, s.get("col", 1)):
            lookup.setdefault(key, set()).add(s["label"])
            n += 1
        counts[s["label"]] = n
    return lookup, counts


# ---------- matching ----------
def build_canon_index(lookup):
    idx = {}
    for k in lookup:
        idx.setdefault(canon(k), set()).add(k)
    return idx


def sheets_to_label(sheets):
    s = sorted(sheets)
    return s[0] if len(s) == 1 else " + ".join(s)


def _resolve(hits, lookup):
    if len(hits) == 1:
        k = next(iter(hits))
        return sheets_to_label(lookup[k]), k
    memberships = {frozenset(lookup[k]) for k in hits}
    if len(memberships) == 1:
        k = sorted(hits)[0]
        return sheets_to_label(lookup[k]), k
    return "AMBIGUOUS", "/".join(sorted(hits))


def match_sku(text, lookup, canon_index):
    """Return (label, matched_key). label is a sheet label, 'A + B', 'AMBIGUOUS', or None."""
    key = norm(text)
    if not key:
        return None, None
    if key in lookup:
        return sheets_to_label(lookup[key]), key
    if len(key) < 3:
        return None, None
    ckey = canon(key)
    hits = canon_index.get(ckey)
    if hits:
        return _resolve(hits, lookup)
    close = difflib.get_close_matches(ckey, canon_index.keys(), n=1, cutoff=FUZZY_CUTOFF)
    if close:
        return _resolve(canon_index[close[0]], lookup)
    return None, None
