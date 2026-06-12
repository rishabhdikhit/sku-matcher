"""
SKU matcher dashboard — manage the source sheets from any device on your WiFi.

Run:  python dashboard.py
Then open the printed URL. On your phone (Android or iPhone), open the
http://<laptop-ip>:5000 URL shown — same WiFi required.

What you can do here:
  - add a CSV sheet (upload + label + which column holds the SKU)
  - download or remove a sheet
  - test a SKU to see which sheet(s) it's in
  - launch the desktop scanner (opens the camera window on the laptop)
"""

import os
import sys
import socket
import subprocess

from flask import (Flask, request, redirect, url_for,
                   send_from_directory, render_template_string)

import sheetstore as ss

app = Flask(__name__)


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


PAGE = """
<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SKU Matcher</title>
<style>
  :root{--bg:#0e1116;--card:#171c24;--line:#2a323d;--ink:#e6edf3;--mut:#8b96a5;--acc:#3b82f6}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;padding:18px;max-width:760px;margin:auto}
  h1{font-size:20px;margin:.2em 0}
  .mut{color:var(--mut)}
  .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:14px 0}
  .phone{background:#0d2538;border-color:#1e4a6b}
  table{width:100%;border-collapse:collapse}
  th,td{text-align:left;padding:8px 6px;border-bottom:1px solid var(--line);font-size:14px}
  th{color:var(--mut);font-weight:600}
  a{color:var(--acc);text-decoration:none}
  input,button{font:inherit}
  input[type=text],input[type=number],input[type=file]{background:#0e1116;border:1px solid var(--line);color:var(--ink);border-radius:8px;padding:8px 10px;width:100%}
  label{display:block;font-size:13px;color:var(--mut);margin:8px 0 3px}
  button{background:var(--acc);border:0;color:#fff;border-radius:8px;padding:9px 14px;cursor:pointer;font-weight:600}
  button.ghost{background:#2a323d}
  button.danger{background:#7f1d1d}
  .row{display:flex;gap:10px;flex-wrap:wrap}
  .row>div{flex:1;min-width:120px}
  .pill{display:inline-block;background:#0e1116;border:1px solid var(--line);border-radius:20px;padding:3px 10px;font-size:13px;margin-right:6px}
  .flash{background:#14321f;border:1px solid #1f7a44;padding:10px 12px;border-radius:8px;margin:10px 0}
  code{background:#0e1116;padding:2px 6px;border-radius:6px;border:1px solid var(--line)}
</style></head><body>
<h1>SKU → Sheet dashboard</h1>
<div class="mut">{{ total }} unique SKUs across {{ sheets|length }} sheets · {{ overlap }} in more than one sheet</div>

{% if result %}<div class="flash">{{ result }}</div>{% endif %}

<div class="card phone">
  <b>Open on your phone</b> (Android or iPhone, same WiFi):<br>
  <code>http://{{ ip }}:5000</code>
</div>

<div class="card">
  <b>Sheets</b>
  <table>
    <tr><th>Label</th><th>File</th><th>SKUs</th><th></th></tr>
    {% for s in sheets %}
    <tr>
      <td><span class="pill">{{ s.label }}</span></td>
      <td class="mut">{{ s.file }} · col {{ s.col }}</td>
      <td>{{ counts.get(s.label, 0) }}</td>
      <td>
        <a href="{{ url_for('download', sid=s.id) }}">download</a> ·
        <form method="post" action="{{ url_for('remove', sid=s.id) }}" style="display:inline"
              onsubmit="return confirm('Remove {{ s.label }}?')">
          <button class="danger" style="padding:3px 9px">remove</button></form>
      </td>
    </tr>
    {% else %}
    <tr><td colspan="4" class="mut">No sheets yet — add one below.</td></tr>
    {% endfor %}
  </table>
</div>

<div class="card">
  <b>Add a sheet</b>
  <form method="post" action="{{ url_for('add') }}" enctype="multipart/form-data">
    <div class="row">
      <div><label>Label (e.g. Sheet 3)</label><input type="text" name="label" required></div>
      <div><label>SKU column (0-based)</label><input type="number" name="col" value="1" min="0"></div>
    </div>
    <label>CSV file</label><input type="file" name="file" accept=".csv" required>
    <div style="margin-top:12px"><button>Add sheet</button></div>
  </form>
</div>

<div class="card">
  <b>Scan history</b> <span class="mut">{{ hist_total }} scans · {{ hist_distinct }} distinct</span>
  <div style="margin:10px 0">
    <a href="{{ url_for('history_csv') }}"><button class="ghost" type="button">Download CSV</button></a>
    <form method="post" action="{{ url_for('history_clear') }}" style="display:inline"
          onsubmit="return confirm('Clear all scan history?')">
      <button class="danger">Clear</button></form>
  </div>
  <table>
    <tr><th>Time</th><th>SKU</th><th>Sheet</th><th>Source</th></tr>
    {% for r in history %}
    <tr><td class="mut">{{ r.time }}</td><td>{{ r.sku }}</td>
        <td><span class="pill">{{ r.sheet }}</span></td><td class="mut">{{ r.source }}</td></tr>
    {% else %}
    <tr><td colspan="4" class="mut">No scans yet — start the scanner and hold a SKU up.</td></tr>
    {% endfor %}
  </table>
  {% if hist_total > 50 %}<div class="mut" style="margin-top:6px">Showing latest 50 · download for all.</div>{% endif %}
</div>

<div class="card">
  <b>Test a SKU</b>
  <form method="post" action="{{ url_for('test') }}">
    <div class="row">
      <div><input type="text" name="sku" placeholder="type or paste a SKU" required></div>
      <div style="flex:0"><button class="ghost">Check</button></div>
    </div>
  </form>
</div>

<div class="card">
  <b>Start the camera scanner</b> <span class="mut">(window opens on the laptop)</span>
  <form method="post" action="{{ url_for('launch') }}">
    <label><b>Phone camera IP</b> — the address your phone's webcam app shows,
      e.g. <code>192.168.29.252:8080</code> (Android: IP Webcam · iPhone: IP Camera Lite)</label>
    <div class="row">
      <div><input type="text" name="phone" value="{{ phone }}" placeholder="192.168.29.252:8080"></div>
      <div style="flex:0"><button name="mode" value="phone">Start phone scan</button></div>
    </div>
    <div style="margin-top:10px">
      <button class="ghost" name="mode" value="laptop">Use laptop camera instead</button>
    </div>
  </form>
</div>
</body></html>
"""


def build_phone_url(raw):
    """Turn '192.168.1.5', '192.168.1.5:8080' or a full URL into a video stream URL."""
    raw = (raw or "").strip()
    if not raw:
        return None
    raw = raw.replace("http://", "").replace("https://", "").strip("/")
    host, _, path = raw.partition("/")
    if ":" not in host:
        host += ":8080"            # IP Webcam default port
    if not path:
        path = "video"             # IP Webcam stream path
    return f"http://{host}/{path}"


@app.route("/")
def index():
    cfg = ss.load_config()
    lookup, counts = ss.build_lookup(cfg)
    overlap = sum(1 for v in lookup.values() if len(v) > 1)
    hist = ss.read_history()
    return render_template_string(PAGE, sheets=cfg, counts=counts,
                                  total=len(lookup), overlap=overlap,
                                  ip=lan_ip(), phone=ss.get_setting("phone"),
                                  history=list(reversed(hist))[:50],
                                  hist_total=len(hist),
                                  hist_distinct=len({r["sku"] for r in hist}),
                                  result=request.args.get("result"))


@app.route("/add", methods=["POST"])
def add():
    f = request.files.get("file")
    label = (request.form.get("label") or "").strip()
    try:
        col = int(request.form.get("col") or 1)
    except ValueError:
        col = 1
    if f and f.filename and label:
        os.makedirs(ss.DATA_DIR, exist_ok=True)
        fname = ss.unique_name(label)
        f.save(os.path.join(ss.DATA_DIR, fname))
        ss.add_sheet(label, fname, col)
        return redirect(url_for("index", result=f"Added sheet '{label}'."))
    return redirect(url_for("index", result="Need both a label and a CSV file."))


@app.route("/remove/<int:sid>", methods=["POST"])
def remove(sid):
    s = ss.get_sheet(sid)
    ss.remove_sheet(sid)
    return redirect(url_for("index", result=f"Removed '{s['label']}'." if s else "Removed."))


@app.route("/download/<int:sid>")
def download(sid):
    s = ss.get_sheet(sid)
    if s:
        return send_from_directory(ss.DATA_DIR, s["file"], as_attachment=True)
    return redirect(url_for("index", result="Sheet not found."))


@app.route("/test", methods=["POST"])
def test():
    sku = (request.form.get("sku") or "").strip()
    lookup, _ = ss.build_lookup()
    ci = ss.build_canon_index(lookup)
    label, hit = ss.match_sku(sku, lookup, ci)
    if label:
        msg = f"'{sku}' → {label}" + (f"  (matched {hit})" if hit and ss.norm(hit) != ss.norm(sku) else "")
    else:
        msg = f"'{sku}' → NOT FOUND in any sheet"
    return redirect(url_for("index", result=msg))


@app.route("/history.csv")
def history_csv():
    if os.path.exists(ss.HISTORY_FILE):
        return send_from_directory(ss.HERE, "history.csv", as_attachment=True,
                                   download_name="scan_history.csv")
    return redirect(url_for("index", result="No scan history yet."))


@app.route("/history/clear", methods=["POST"])
def history_clear():
    ss.clear_history()
    return redirect(url_for("index", result="Scan history cleared."))


@app.route("/launch", methods=["POST"])
def launch():
    mode = request.form.get("mode", "phone")
    if mode == "laptop":
        src = "0"
    else:
        phone = (request.form.get("phone") or "").strip()
        ss.set_setting("phone", phone)          # remember it for next time
        src = build_phone_url(phone) or "0"
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    subprocess.Popen([sys.executable, os.path.join(ss.HERE, "sku_match.py"),
                      "--source", src], cwd=ss.HERE, env=env)
    return redirect(url_for("index", result=f"Scanner launched on the laptop (source: {src})."))


if __name__ == "__main__":
    ss.ensure_config()
    ip = lan_ip()
    print("\nSKU matcher dashboard")
    print(f"  This laptop : http://127.0.0.1:5000")
    print(f"  Your phone  : http://{ip}:5000   (Android/iPhone, same WiFi)\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
