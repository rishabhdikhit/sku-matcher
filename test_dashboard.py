"""Smoke test the dashboard routes without a browser."""
import io
import sheetstore as ss
import dashboard

ss.ensure_config()
c = dashboard.app.test_client()

r = c.get("/")
assert r.status_code == 200, r.status_code
assert b"dashboard" in r.data.lower()
print("GET /            ok (200)")

# add a tiny new sheet
csv_bytes = b"label,sku\nignore,TEST-AAA-1\nignore,TEST-BBB-2\n"
r = c.post("/add", data={"label": "Sheet 3", "col": "1",
                         "file": (io.BytesIO(csv_bytes), "s3.csv")},
           content_type="multipart/form-data", follow_redirects=True)
assert r.status_code == 200
labels = [s["label"] for s in ss.load_config()]
assert "Sheet 3" in labels, labels
print("POST /add        ok ->", labels)

# test a SKU from the new sheet
r = c.post("/test", data={"sku": "test aaa 1"}, follow_redirects=True)
assert b"Sheet 3" in r.data, "test SKU did not resolve to Sheet 3"
print("POST /test       ok (TEST-AAA-1 -> Sheet 3)")

# remove the new sheet again
sid = next(s["id"] for s in ss.load_config() if s["label"] == "Sheet 3")
r = c.post(f"/remove/{sid}", follow_redirects=True)
assert "Sheet 3" not in [s["label"] for s in ss.load_config()]
print("POST /remove     ok (Sheet 3 gone)")
print("\nALL DASHBOARD ROUTES OK")
