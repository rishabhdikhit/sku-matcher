import pandas as pd

FILES = [
    (r"C:\Users\Lenovo\Downloads\01.csv", "Sheet 1"),
    (r"C:\Users\Lenovo\Downloads\02.csv", "Sheet 2"),
]
SKU_COL = 1  # 0-based: 2nd column holds the code

def load(path):
    df = pd.read_csv(path, header=None, dtype=str, keep_default_na=False)
    vals = []
    for v in df[SKU_COL]:
        v = str(v).strip()
        if v and v.upper() not in ("SIZE", "TOTAL", "COUNT"):
            vals.append(v.upper())
    return vals

s1_list = load(FILES[0][0])
s2_list = load(FILES[1][0])
s1, s2 = set(s1_list), set(s2_list)

print(f"Sheet 1: {len(s1_list)} rows, {len(s1)} unique")
print(f"Sheet 2: {len(s2_list)} rows, {len(s2)} unique")
print(f"In BOTH sheets: {len(s1 & s2)}")
print(f"Only Sheet 1 : {len(s1 - s2)}")
print(f"Only Sheet 2 : {len(s2 - s1)}")

dup1 = len(s1_list) - len(s1)
dup2 = len(s2_list) - len(s2)
print(f"Dupes within Sheet 1: {dup1}   within Sheet 2: {dup2}")

print("\nShared SKUs (can't be disambiguated):")
for x in sorted(s1 & s2):
    print("  ", x)
