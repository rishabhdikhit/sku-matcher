"""Offline check of the data layer + matcher (no camera)."""
import sheetstore as ss

cfg = ss.ensure_config()
lookup, counts = ss.build_lookup(cfg)
ci = ss.build_canon_index(lookup)
both = sum(1 for v in lookup.values() if len(v) > 1)
print(f"Sheets: {[s['label'] for s in cfg]}")
print(f"Unique SKUs: {len(lookup)}  | counts: {counts}  | in >1 sheet: {both}")

# Build live test cases from the real data so we never hardcode SKUs.
single = next((k for k, v in lookup.items() if len(v) == 1), None)
multi = next((k for k, v in lookup.items() if len(v) > 1), None)

def show(name, sku):
    if sku is None:
        print(f"  {name}: (none in data)"); return
    label, hit = ss.match_sku(sku, lookup, ci)
    print(f"  {name}: {sku!r} -> {label}  (matched {hit})")

show("single-sheet", single)
show("multi-sheet ", multi)
# OCR-style slip: swap a 0 for letter O in the single-sheet SKU
if single and "0" in single:
    show("with O/0 slip", single.replace("0", "O", 1))
show("not found   ", "ZZ-NOPE-999")
