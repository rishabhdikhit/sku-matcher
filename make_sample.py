import os
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
out = os.path.join(HERE, "skus.xlsx")

with pd.ExcelWriter(out) as w:
    pd.DataFrame({"SKU": ["ABC123", "ABC124", "RED-100"]}).to_excel(
        w, sheet_name="Sheet1", index=False)
    pd.DataFrame({"SKU": ["XYZ900", "BLUE-200", "ZZ-777"]}).to_excel(
        w, sheet_name="Sheet2", index=False)

print("wrote", out)
