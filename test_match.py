import sku_match as m

lookup = m.load_sheets()
tests = [
    "4MSS2961-03-L",   # only Sheet 1
    "4MST3206-03-S",   # only Sheet 2
    "BP0026-04",       # both
    "4MSR5251-03-32",  # both
    "4MSS296I-03-L",   # Sheet 1 with OCR slip (I instead of 1)
    "bp 0025-01",      # both, lowercase + space
    "NOPE-999",        # not found
]
for t in tests:
    label, hit = m.match_sku(t, lookup)
    print(f"  {t!r:18} -> {str(label):12} (matched {hit})")
