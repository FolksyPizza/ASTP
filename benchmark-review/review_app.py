#!/usr/bin/env python3
"""MCTP-Bench review app.

A local, full-audit viewer for a benchmark results store, with grading and flagging that persist
to SQLite next to the store. Standard library only, so it runs on any Python 3 with no installs:

    python3 review_app.py --results /path/to/results --port 8080

It indexes results/runs/<suite>/<model>/<condition>.jsonl into SQLite on first run, serves a
single-page UI, and reads each run's prompt / output / reasoning / timeline / raw capture on
demand. Reviews (grade, flags, note) are written to review.db and never touch the run records.
"""
import argparse
import glob
import json
import os
import re
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

RESULTS_DIR = ""
DB_PATH = ""
_LOCAL = threading.local()

COLS = [
    ("run_id", "TEXT"), ("suite", "TEXT"), ("model", "TEXT"), ("condition", "TEXT"),
    ("instance", "TEXT"), ("tier", "TEXT"), ("task_id", "TEXT"), ("trial", "INTEGER"),
    ("objective_pass", "INTEGER"), ("started_at", "TEXT"), ("ttft_s", "REAL"),
    ("latency_s", "REAL"), ("prompt_tokens", "INTEGER"), ("output_tokens", "INTEGER"),
    ("reasoning_tokens", "INTEGER"), ("context_tokens", "INTEGER"),
    ("context_tokens_original", "INTEGER"), ("context_truncated", "INTEGER"),
    ("max_tokens", "INTEGER"), ("temperature", "REAL"), ("seed", "INTEGER"),
    ("model_size_b", "REAL"), ("tokps", "REAL"),
]


def db():
    if not hasattr(_LOCAL, "conn"):
        _LOCAL.conn = sqlite3.connect(DB_PATH, timeout=30)
        _LOCAL.conn.row_factory = sqlite3.Row
        _LOCAL.conn.execute("PRAGMA journal_mode=WAL")
    return _LOCAL.conn


def _pass_int(v):
    return 1 if v is True else 0 if v is False else None


def instance_of(endpoint):
    e = endpoint or ""
    if "11434" in e:
        return "3090 · Ollama"
    if ":8000" in e:
        return "3060 · vLLM"
    host = e.split("//")[-1].split("/")[0]
    return host or "unknown"


def build_index(rebuild=False):
    conn = sqlite3.connect(DB_PATH)
    have = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='runs'").fetchone()
    if have and not rebuild:
        n = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        conn.close()
        print(f"index: {n:,} runs already indexed (use --rebuild to refresh)")
        return
    print("building index from run records ...")
    conn.execute("DROP TABLE IF EXISTS runs")
    conn.execute(f"CREATE TABLE runs ({', '.join(f'{c} {t}' for c, t in COLS)}, record TEXT)")
    conn.execute("""CREATE TABLE IF NOT EXISTS reviews (
        run_id TEXT PRIMARY KEY, grade TEXT, flags TEXT, note TEXT, updated_at TEXT)""")
    rows = []
    shards = glob.glob(os.path.join(RESULTS_DIR, "runs", "*", "*", "*.jsonl"))
    for path in shards:
        if path.endswith(".bak"):
            continue
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                lat, ttft = r.get("latency_s") or 0, r.get("ttft_s") or 0
                out = r.get("output_tokens") or 0
                tokps = out / (lat - ttft) if lat and (lat - ttft) > 0.01 else None
                vals = []
                for c, _ in COLS:
                    if c == "objective_pass":
                        vals.append(_pass_int(r.get("objective_pass")))
                    elif c == "instance":
                        vals.append(instance_of(r.get("endpoint")))
                    elif c == "tokps":
                        vals.append(round(tokps, 2) if tokps else None)
                    else:
                        vals.append(r.get(c))
                rows.append(vals + [line])
    ph = ", ".join("?" * (len(COLS) + 1))
    conn.executemany(f"INSERT INTO runs VALUES ({ph})", rows)
    for c in ("suite", "model", "condition", "instance", "objective_pass"):
        conn.execute(f"CREATE INDEX idx_{c} ON runs({c})")
    conn.commit()
    print(f"index: {len(rows):,} runs indexed from {len(shards)} shards")
    conn.close()


def read_ref(ref, cap=4_000_000):
    if not ref:
        return None
    path = ref if os.path.isabs(ref) else os.path.join(RESULTS_DIR, ref)
    if not os.path.exists(path):
        return None
    with open(path, errors="replace") as f:
        data = f.read(cap + 1)
    return data[:cap] + "\n\n[... truncated ...]" if len(data) > cap else data


def api_stats():
    conn = db()
    total = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    graded = conn.execute("SELECT COUNT(*) FROM reviews WHERE grade IS NOT NULL AND grade!=''").fetchone()[0]
    flagged = conn.execute("SELECT COUNT(*) FROM reviews WHERE flags IS NOT NULL AND flags!=''").fetchone()[0]
    facets = {}
    for col in ("suite", "model", "condition", "instance"):
        facets[col] = [row[0] for row in conn.execute(
            f"SELECT DISTINCT {col} FROM runs WHERE {col} IS NOT NULL ORDER BY {col}")]
    # Aggregate pass/fail/none + token/latency means per (suite, model, condition).
    agg = [dict(r) for r in conn.execute("""
        SELECT suite, model, condition,
          COUNT(*) n,
          SUM(CASE WHEN objective_pass=1 THEN 1 ELSE 0 END) npass,
          SUM(CASE WHEN objective_pass=0 THEN 1 ELSE 0 END) nfail,
          SUM(CASE WHEN objective_pass IS NULL THEN 1 ELSE 0 END) nnone,
          ROUND(AVG(context_tokens),0) ctx, ROUND(AVG(output_tokens),0) out,
          ROUND(AVG(latency_s),2) lat
        FROM runs GROUP BY suite, model, condition ORDER BY suite, model, condition""")]
    return {"total": total, "graded": graded, "flagged": flagged, "facets": facets, "agg": agg}


_SORTABLE = {"started_at", "latency_s", "ttft_s", "output_tokens", "prompt_tokens",
             "context_tokens", "tokps", "objective_pass", "run_id", "suite", "model"}


def api_runs(q):
    conn = db()
    where, args = [], []
    for col in ("suite", "model", "condition", "instance"):
        v = q.get(col, [""])[0]
        if v:
            where.append(f"r.{col}=?")
            args.append(v)
    pv = q.get("pass", [""])[0]
    if pv == "pass":
        where.append("r.objective_pass=1")
    elif pv == "fail":
        where.append("r.objective_pass=0")
    elif pv == "none":
        where.append("r.objective_pass IS NULL")
    if q.get("flagged", [""])[0] == "1":
        where.append("rv.flags IS NOT NULL AND rv.flags!=''")
    if q.get("graded", [""])[0] == "1":
        where.append("rv.grade IS NOT NULL AND rv.grade!=''")
    if q.get("ungraded", [""])[0] == "1":
        where.append("(rv.grade IS NULL OR rv.grade='')")
    term = q.get("q", [""])[0].strip()
    if term:
        where.append("(r.task_id LIKE ? OR r.run_id LIKE ?)")
        args += [f"%{term}%", f"%{term}%"]
    sort = q.get("sort", ["started_at"])[0]
    sort = sort if sort in _SORTABLE else "started_at"
    direction = "DESC" if q.get("dir", ["desc"])[0] == "desc" else "ASC"
    page = max(1, int(q.get("page", ["1"])[0] or 1))
    size = min(300, max(10, int(q.get("size", ["60"])[0] or 60)))
    wsql = ("WHERE " + " AND ".join(where)) if where else ""
    base = f"FROM runs r LEFT JOIN reviews rv ON rv.run_id=r.run_id {wsql}"
    total = conn.execute(f"SELECT COUNT(*) {base}", args).fetchone()[0]
    sql = (f"SELECT r.run_id, r.suite, r.model, r.condition, r.instance, r.trial, "
           f"r.objective_pass, r.output_tokens, r.context_tokens, r.latency_s, r.tokps, "
           f"rv.grade, rv.flags {base} ORDER BY r.{sort} {direction} LIMIT ? OFFSET ?")
    runs = [dict(row) for row in conn.execute(sql, args + [size, (page - 1) * size])]
    return {"total": total, "page": page, "size": size, "runs": runs}


def api_run(run_id):
    conn = db()
    row = conn.execute("SELECT record FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if not row:
        return None
    rec = json.loads(row["record"])
    rv = conn.execute("SELECT grade, flags, note FROM reviews WHERE run_id=?", (run_id,)).fetchone()
    review = dict(rv) if rv else {"grade": "", "flags": "", "note": ""}
    texts = {k: read_ref(rec.get(k + "_ref")) for k in
             ("prompt", "output", "reasoning", "timeline", "raw")}
    pipeline = None
    if rec.get("suite") == "swarm":
        m = re.search(r"^(.*)/s\d+_", rec.get("task_id", ""))
        if m:
            prefix = m.group(1)
            stages = []
            for r2 in conn.execute(
                    "SELECT record FROM runs WHERE task_id LIKE ? AND model=? AND condition=? "
                    "AND trial=? ORDER BY task_id", (prefix + "/s%", rec.get("model"),
                    rec.get("condition"), rec.get("trial"))):
                s = json.loads(r2["record"])
                sid = s.get("task_id", "")
                stages.append({"run_id": s.get("run_id"),
                               "role": sid.split("/")[-1] if "/" in sid else sid,
                               "objective_pass": _pass_int(s.get("objective_pass")),
                               "output": read_ref(s.get("output_ref")),
                               "context_tokens": s.get("context_tokens")})
            pipeline = {"prefix": prefix, "stages": stages}
    return {"record": rec, "review": review, "texts": texts, "pipeline": pipeline,
            "instance": instance_of(rec.get("endpoint"))}


def api_save_review(body):
    conn = db()
    rid = body.get("run_id")
    if not rid:
        return {"ok": False}
    conn.execute("""INSERT INTO reviews(run_id, grade, flags, note, updated_at) VALUES(?,?,?,?,?)
        ON CONFLICT(run_id) DO UPDATE SET grade=excluded.grade, flags=excluded.flags,
        note=excluded.note, updated_at=excluded.updated_at""",
        (rid, body.get("grade", ""), body.get("flags", ""), body.get("note", ""),
         time.strftime("%Y-%m-%dT%H:%M:%S")))
    conn.commit()
    return {"ok": True}


def api_export():
    conn = db()
    out = ["run_id,suite,model,condition,instance,objective_pass,grade,flags,note"]
    for row in conn.execute("""SELECT r.run_id, r.suite, r.model, r.condition, r.instance,
        r.objective_pass, rv.grade, rv.flags, rv.note FROM reviews rv JOIN runs r ON r.run_id=rv.run_id"""):
        note = (row["note"] or "").replace('"', '""').replace("\n", " ")
        out.append(f'{row["run_id"]},{row["suite"]},{row["model"]},{row["condition"]},'
                   f'{row["instance"]},{row["objective_pass"]},{row["grade"] or ""},'
                   f'"{row["flags"] or ""}","{note}"')
    return "\n".join(out)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body)
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/":
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if u.path == "/api/stats":
            return self._send(200, api_stats())
        if u.path == "/api/runs":
            return self._send(200, api_runs(q))
        if u.path.startswith("/api/run/"):
            r = api_run(u.path[len("/api/run/"):])
            return self._send(200, r) if r else self._send(404, {"error": "not found"})
        if u.path == "/api/export":
            return self._send(200, api_export(), "text/csv")
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        if u.path == "/api/review":
            return self._send(200, api_save_review(body))
        return self._send(404, {"error": "not found"})


PAGE = r"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>MCTP-Bench Review</title>
<style>
:root{
  --bg:#fff; --panel:#f6f7f9; --panel2:#eceff3; --text:#161a1f; --dim:#697280;
  --border:#dfe3e8; --accent:#2563eb; --pass:#0f9d58; --fail:#d93025; --none:#9aa0a6;
  --flag:#c2760a; --sel:rgba(37,99,235,.14); --radius:4px;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
:root[data-theme=dark]{
  --bg:#0d1117; --panel:#161b22; --panel2:#1e2531; --text:#e6edf3; --dim:#8b949e;
  --border:#2a313c; --accent:#4c8dff; --pass:#3fb950; --fail:#f85149; --none:#6e7681;
  --flag:#e3a008; --sel:rgba(76,141,255,.18);
}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--text);font:13px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;overflow:hidden}
header{height:44px;display:flex;align-items:center;gap:14px;padding:0 12px;border-bottom:1px solid var(--border);background:var(--panel)}
header .title{font-weight:650}
header .stat{color:var(--dim);font-size:12px;display:flex;gap:5px;align-items:center}
header .stat b{color:var(--text);font-variant-numeric:tabular-nums}
.bar{height:5px;width:90px;background:var(--panel2);border-radius:9px;overflow:hidden;border:1px solid var(--border)}
.bar>i{display:block;height:100%;background:var(--accent)}
.spacer{flex:1}
button,select,input,textarea{font:inherit;color:var(--text);background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:5px 8px}
button{cursor:pointer;background:var(--panel2)} button:hover{border-color:var(--accent)} .ghost{background:transparent}
main{display:flex;height:calc(100% - 44px)}
.list{width:640px;min-width:340px;display:flex;flex-direction:column;overflow:hidden}
.divider{width:6px;cursor:col-resize;background:var(--border);flex:0 0 auto}
.divider:hover{background:var(--accent)}
.filters{display:flex;flex-wrap:wrap;gap:6px;padding:8px;border-bottom:1px solid var(--border);background:var(--panel)}
.filters select,.filters input{padding:4px 6px;font-size:12px}
.filters input[type=search]{flex:1;min-width:110px}
.tblwrap{overflow:auto;flex:1}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--border);white-space:nowrap}
th{position:sticky;top:0;background:var(--panel);cursor:pointer;font-size:11px;font-weight:600;color:var(--dim);text-transform:uppercase;letter-spacing:.3px;z-index:1}
tbody tr{cursor:pointer} tbody tr:hover{background:var(--panel2)} tbody tr.sel{background:var(--sel)}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
.badge{display:inline-block;min-width:36px;text-align:center;padding:1px 6px;border-radius:var(--radius);font-size:11px;font-weight:600;color:#fff}
.b-pass{background:var(--pass)}.b-fail{background:var(--fail)}.b-none{background:var(--none)}
.pill{font-size:11px;color:var(--dim);border:1px solid var(--border);border-radius:9px;padding:0 6px}
.dot{color:var(--flag)}
.pager{display:flex;align-items:center;gap:8px;padding:7px 8px;border-top:1px solid var(--border);background:var(--panel);font-size:12px}
.detail{flex:1;overflow:auto;padding:14px 16px;min-width:320px}
.detail h2{margin:0 0 2px;font-size:15px;display:flex;align-items:center;gap:8px}
.sub{color:var(--dim);font-size:12px;margin-bottom:12px}
.review{background:var(--panel);border:1px solid var(--border);border-radius:var(--radius);padding:10px;margin-bottom:14px}
.review .row{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
.review .lbl{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.3px;width:44px}
.chip{padding:3px 10px;border:1px solid var(--border);border-radius:var(--radius);cursor:pointer;background:var(--bg);font-size:12px}
.chip:hover{border-color:var(--accent)}
.chip.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.chip.g-correct.on{background:var(--pass);border-color:var(--pass)}
.chip.g-incorrect.on{background:var(--fail);border-color:var(--fail)}
textarea{width:100%;min-height:44px;resize:vertical;font-family:var(--mono);font-size:12px}
.saved{color:var(--pass);font-size:12px}
.metatable{width:100%;border-collapse:collapse;margin-bottom:14px;border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}
.metatable td{border-bottom:1px solid var(--border);padding:5px 10px;vertical-align:top}
.metatable tr:last-child td{border-bottom:none}
.metatable tr:hover{background:var(--panel)}
.metatable td.mk{color:var(--dim);text-transform:uppercase;font-size:10.5px;letter-spacing:.3px;width:190px;white-space:nowrap;background:var(--panel)}
.metatable td.mv{font-family:var(--mono);font-size:12.5px;word-break:break-word;overflow-wrap:anywhere}
.tabs{display:flex;gap:2px;border-bottom:1px solid var(--border);align-items:center}
.tab{padding:6px 12px;cursor:pointer;border:1px solid transparent;border-bottom:none;color:var(--dim);font-size:12px}
.tab.on{color:var(--text);background:var(--panel);border-color:var(--border);border-radius:var(--radius) var(--radius) 0 0}
.tab .empty{opacity:.4}
pre.text{margin:0;background:var(--panel);border:1px solid var(--border);border-top:none;padding:11px;white-space:pre-wrap;word-break:break-word;font-family:var(--mono);font-size:12.5px;line-height:1.5;overflow:auto;resize:vertical;height:46vh}
.placeholder{color:var(--dim);padding:44px;text-align:center}
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.45);display:none;align-items:flex-start;justify-content:center;padding:40px 20px;z-index:10}
.overlay.on{display:flex}
.modal{background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);max-width:1000px;width:100%;max-height:85vh;overflow:auto;padding:16px}
.modal h3{margin:0 0 10px}
.statgrid table{font-size:12px}
.statgrid td,.statgrid th{white-space:nowrap;padding:4px 10px}
.hint{color:var(--dim);font-size:11px}
kbd{font-family:var(--mono);background:var(--panel2);border:1px solid var(--border);border-radius:3px;padding:0 4px;font-size:11px}
.stage{border:1px solid var(--border);border-radius:var(--radius);margin-bottom:8px;overflow:hidden}
.stagehd{display:flex;gap:10px;align-items:center;padding:6px 10px;background:var(--panel);font-size:12px}
.srole{font-weight:600;font-family:var(--mono)}
.stagetext{margin:0;padding:9px 10px;white-space:pre-wrap;word-break:break-word;font-family:var(--mono);font-size:12px;max-height:220px;overflow:auto;background:var(--bg)}
</style></head><body>
<header>
  <span class=title>MCTP-Bench Review</span>
  <span class=stat><b id=s-total>0</b> runs</span>
  <span class=stat>graded <div class=bar><i id=s-bar></i></div><b id=s-graded>0</b></span>
  <span class=stat>flagged <b id=s-flagged>0</b></span>
  <span class=spacer></span>
  <span class=hint>j/k move · 1-4 grade · f flag · n next ungraded</span>
  <button class=ghost id=statsBtn>Statistics</button>
  <button class=ghost id=exportBtn>Export</button>
  <button class=ghost id=themeBtn>Theme</button>
</header>
<main>
  <div class=list id=list>
    <div class=filters>
      <select id=f-suite></select><select id=f-model></select><select id=f-instance></select>
      <select id=f-condition></select>
      <select id=f-pass><option value=''>pass: any</option><option value=pass>pass</option><option value=fail>fail</option><option value=none>none</option></select>
      <select id=f-review><option value=''>review: any</option><option value=graded>graded</option><option value=ungraded>ungraded</option><option value=flagged>flagged</option></select>
      <input type=search id=f-q placeholder='search task / run id'>
    </div>
    <div class=tblwrap><table><thead><tr id=head></tr></thead><tbody id=rows></tbody></table></div>
    <div class=pager>
      <button id=prev>Prev</button><span id=pageinfo class=mono></span><button id=next>Next</button>
      <span class=spacer></span><select id=size><option>60</option><option>120</option><option>300</option></select>
    </div>
  </div>
  <div class=divider id=divider></div>
  <div class=detail id=detail><div class=placeholder>Select a run, or press <kbd>j</kbd> to start.</div></div>
</main>
<div class=overlay id=overlay><div class=modal><h3>Overall statistics</h3><div class=statgrid id=statbody></div></div></div>
<script>
const $=s=>document.querySelector(s), api=(p,o)=>fetch(p,o).then(r=>r.json());
let state={page:1,size:60,sort:'started_at',dir:'desc',sel:null,idx:-1,rows:[]};
const COLS=[['objective_pass','pass'],['run_id','run'],['suite','suite'],['model','model'],['instance','instance'],['condition','cond'],['output_tokens','out'],['context_tokens','ctx'],['latency_s','lat'],['tokps','tok/s']];
const GRADES=['correct','partial','incorrect','unsure'];
const FLAGS=['scorer-wrong','interesting','bug','revisit'];

function theme(t){document.documentElement.dataset.theme=t;localStorage.mctpTheme=t}
theme(localStorage.mctpTheme||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'));
$('#themeBtn').onclick=()=>theme(document.documentElement.dataset.theme==='dark'?'light':'dark');
$('#exportBtn').onclick=()=>location='/api/export';

// resizable divider
const savedW=+localStorage.mctpListW; if(savedW)$('#list').style.width=savedW+'px';
(function(){let drag=false;
 $('#divider').addEventListener('mousedown',e=>{drag=true;document.body.style.userSelect='none';e.preventDefault()});
 addEventListener('mousemove',e=>{if(!drag)return;const w=Math.max(340,Math.min(e.clientX,innerWidth-360));$('#list').style.width=w+'px';localStorage.mctpListW=w});
 addEventListener('mouseup',()=>{drag=false;document.body.style.userSelect=''});
})();

function badge(p){const c=p===1?'b-pass':p===0?'b-fail':'b-none';const t=p===1?'PASS':p===0?'FAIL':'none';return`<span class="badge ${c}">${t}</span>`}
function fmt(k,v){if(v==null)return'';if(k==='latency_s')return v.toFixed(2)+'s';if(k==='tokps')return v?v.toFixed(0):'';if(k==='run_id')return v.slice(0,8);if(k==='objective_pass')return badge(v);if(k==='model')return v.replace('qwen2.5-','q2.5-').replace('qwen3.8:','q3.8:');return v}

async function loadStats(){
  const s=await api('/api/stats');window._stats=s;
  $('#s-total').textContent=s.total.toLocaleString();
  $('#s-graded').textContent=s.graded.toLocaleString();
  $('#s-flagged').textContent=s.flagged.toLocaleString();
  $('#s-bar').style.width=(s.total?100*s.graded/s.total:0)+'%';
  const fill=(id,vals,label)=>$(id).innerHTML=`<option value=''>${label}</option>`+vals.map(v=>`<option>${v}</option>`).join('');
  fill('#f-suite',s.facets.suite,'suite: all');fill('#f-model',s.facets.model,'model: all');
  fill('#f-instance',s.facets.instance,'instance: all');fill('#f-condition',s.facets.condition,'cond: all');
}
function head(){$('#head').innerHTML=COLS.map(([k,l])=>`<th data-k="${k}">${l}${state.sort===k?(state.dir==='desc'?' ↓':' ↑'):''}</th>`).join('')+'<th>rev</th>';
  document.querySelectorAll('#head th[data-k]').forEach(th=>th.onclick=()=>{const k=th.dataset.k;if(state.sort===k)state.dir=state.dir==='desc'?'asc':'desc';else{state.sort=k;state.dir='desc'}load()})}
function qs(){const p=new URLSearchParams();p.set('page',state.page);p.set('size',state.size);p.set('sort',state.sort);p.set('dir',state.dir);
  for(const f of['suite','model','instance','condition'])if($('#f-'+f).value)p.set(f,$('#f-'+f).value);
  if($('#f-pass').value)p.set('pass',$('#f-pass').value);
  const rev=$('#f-review').value;if(rev)p.set(rev,'1');
  if($('#f-q').value)p.set('q',$('#f-q').value);return p}
async function load(){
  const d=await api('/api/runs?'+qs());head();state.rows=d.runs;
  $('#rows').innerHTML=d.runs.map((r,i)=>`<tr data-id="${r.run_id}" data-i="${i}" class="${r.run_id===state.sel?'sel':''}">`+
    COLS.map(([k])=>`<td class="${['run_id','latency_s','tokps','output_tokens','context_tokens'].includes(k)?'mono':''}">${fmt(k,r[k])}</td>`).join('')+
    `<td>${r.grade?'<span class=pill>'+r.grade[0].toUpperCase()+'</span>':''}${r.flags?' <span class=dot>⚑</span>':''}</td></tr>`).join('');
  document.querySelectorAll('#rows tr').forEach(tr=>tr.onclick=()=>openRow(+tr.dataset.i));
  const pages=Math.max(1,Math.ceil(d.total/d.size));
  $('#pageinfo').textContent=`${d.page} / ${pages} · ${d.total.toLocaleString()} rows`;
  $('#prev').disabled=d.page<=1;$('#next').disabled=d.page>=pages;
}
function openRow(i){if(i<0||i>=state.rows.length)return;state.idx=i;open(state.rows[i].run_id)}
async function open(id){
  state.sel=id;document.querySelectorAll('#rows tr').forEach(t=>t.classList.toggle('sel',t.dataset.id===id));
  const tr=document.querySelector(`#rows tr[data-id="${id}"]`);if(tr)tr.scrollIntoView({block:'nearest'});
  const d=await api('/api/run/'+id);const r=d.record;
  const keys=['suite','model','instance','condition','trial','tier','objective_pass','objective_detail','task_id','started_at','ttft_s','latency_s','tokps','prompt_tokens','output_tokens','reasoning_tokens','context_tokens','context_tokens_original','context_truncated','packet_node_ids','retrieved_ids','retrieved_tokens','prep_tokens','max_tokens','temperature','seed','model_size_b','endpoint','harness_commit'];
  const val=k=>{if(k==='instance')return d.instance;if(k==='tokps'){const l=r.latency_s,t=r.ttft_s;return l&&(l-t)>0.01?(r.output_tokens/(l-t)).toFixed(0)+' tok/s':''}
    let v=r[k];if(v&&typeof v==='object')v=JSON.stringify(v);return v==null?'':String(v)};
  const meta=keys.map(k=>`<tr><td class=mk>${k}</td><td class=mv>${val(k).replace(/</g,'&lt;')}</td></tr>`).join('');
  let grade=d.review.grade||'', fl=new Set((d.review.flags||'').split(',').filter(Boolean));
  const gradeChips=GRADES.map(g=>`<span class="chip g-${g} ${grade===g?'on':''}" data-grade="${g}">${g}</span>`).join('');
  const flagChips=FLAGS.map(f=>`<span class="chip ${fl.has(f)?'on':''}" data-flag="${f}">${f}</span>`).join('');
  const tabs=[['prompt','Prompt'],['output','Output'],['reasoning','Reasoning'],['timeline','Timeline'],['raw','Raw']].filter(([k])=>d.texts[k]);
  $('#detail').innerHTML=`
    <h2><span class=mono>${r.run_id.slice(0,12)}</span> ${badge(r.objective_pass===true?1:r.objective_pass===false?0:null)}</h2>
    <div class=sub>${r.suite} · ${r.model} · ${d.instance} · ${r.condition} · trial ${r.trial}</div>
    <div class=review>
      <div class=row><span class=lbl>grade</span>${gradeChips}</div>
      <div class=row><span class=lbl>flags</span>${flagChips}</div>
      <textarea id=note placeholder='notes'>${(d.review.note||'').replace(/</g,'&lt;')}</textarea>
      <div class=row><span id=savemsg class=hint>autosaves on change</span></div>
    </div>
    <table class=metatable>${meta}</table>
    <div class=tabs>${tabs.map(([k,l])=>`<span class="tab" data-tab="${k}">${l}</span>`).join('')}</div>
    <pre class=text id=tabbody></pre>
    ${d.pipeline?`<div class=sub style="margin:14px 0 6px">Pipeline — ${d.pipeline.stages.length} stages, believed-state carried across each handoff</div><div id=pipeline></div>`:''}`;
  const show=k=>{$('#tabbody').textContent=d.texts[k]||'(none recorded)';document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('on',t.dataset.tab===k))};
  document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>show(t.dataset.tab));
  const first=d.texts.output?'output':(tabs[0]&&tabs[0][0]);
  if(first)show(first);
  if(d.pipeline){$('#pipeline').innerHTML=d.pipeline.stages.map((s,i)=>`<div class=stage><div class=stagehd><span class=srole>s${i} · ${s.role}</span>${s.objective_pass==null?'<span class=pill>no objective</span>':badge(s.objective_pass)}<span class=hint>ctx ${s.context_tokens||0} tok</span></div><pre class=stagetext>${(s.output||'(no output)').replace(/</g,'&lt;')}</pre></div>`).join('')}
  const save=()=>{api('/api/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({run_id:id,grade,flags:[...fl].join(','),note:$('#note').value})}).then(()=>{$('#savemsg').innerHTML='<span class=saved>saved</span>';loadStats();
    const row=state.rows.find(x=>x.run_id===id);if(row){row.grade=grade;row.flags=[...fl].join(',');const c=document.querySelector(`#rows tr[data-id="${id}"] td:last-child`);if(c)c.innerHTML=(grade?'<span class=pill>'+grade[0].toUpperCase()+'</span>':'')+(fl.size?' <span class=dot>⚑</span>':'')}})};
  window._setGrade=g=>{grade=grade===g?'':g;document.querySelectorAll('[data-grade]').forEach(x=>x.classList.toggle('on',x.dataset.grade===grade));save()};
  window._toggleFlag=f=>{fl.has(f)?fl.delete(f):fl.add(f);document.querySelectorAll('[data-flag]').forEach(x=>x.classList.toggle('on',fl.has(x.dataset.flag)));save()};
  document.querySelectorAll('[data-grade]').forEach(c=>c.onclick=()=>window._setGrade(c.dataset.grade));
  document.querySelectorAll('[data-flag]').forEach(c=>c.onclick=()=>window._toggleFlag(c.dataset.flag));
  $('#note').onchange=save;
}
// statistics modal
$('#statsBtn').onclick=()=>{const s=window._stats;if(!s)return;
  const rows=s.agg.map(a=>{const rate=a.n?100*a.npass/a.n:0;return`<tr><td>${a.suite}</td><td>${a.model.replace('qwen','q')}</td><td>${a.condition}</td><td class=mono>${a.n}</td><td class=mono>${rate.toFixed(1)}%</td><td class=mono>${a.nnone||''}</td><td class=mono>${a.ctx}</td><td class=mono>${a.out}</td><td class=mono>${a.lat}s</td></tr>`}).join('');
  $('#statbody').innerHTML=`<table><thead><tr><th>suite</th><th>model</th><th>cond</th><th>n</th><th>pass</th><th>none</th><th>ctx tok</th><th>out tok</th><th>lat</th></tr></thead><tbody>${rows}</tbody></table>`;
  $('#overlay').classList.add('on')};
$('#overlay').onclick=e=>{if(e.target===$('#overlay'))$('#overlay').classList.remove('on')};

$('#prev').onclick=()=>{if(state.page>1){state.page--;load()}};
$('#next').onclick=()=>{state.page++;load()};
$('#size').onchange=e=>{state.size=+e.target.value;state.page=1;load()};
['f-suite','f-model','f-instance','f-condition','f-pass','f-review'].forEach(id=>$('#'+id).onchange=()=>{state.page=1;load()});
let tmr;$('#f-q').oninput=()=>{clearTimeout(tmr);tmr=setTimeout(()=>{state.page=1;load()},250)};

// keyboard: j/k move, 1-4 grade, f flag revisit, n next ungraded, Esc close modal
addEventListener('keydown',e=>{
  if(e.target.tagName==='TEXTAREA'||e.target.tagName==='INPUT'||e.target.tagName==='SELECT')return;
  if(e.key==='Escape')$('#overlay').classList.remove('on');
  if(e.key==='j'){openRow(state.idx+1);e.preventDefault()}
  if(e.key==='k'){openRow(state.idx-1);e.preventDefault()}
  if(['1','2','3','4'].includes(e.key)&&window._setGrade){window._setGrade(GRADES[+e.key-1])}
  if(e.key==='f'&&window._toggleFlag){window._toggleFlag('revisit')}
  if(e.key==='n'){const i=state.rows.findIndex((r,ix)=>ix>state.idx&&!r.grade);if(i>=0)openRow(i)}
});
loadStats().then(load);
</script></body></html>"""


def main():
    global RESULTS_DIR, DB_PATH
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=os.path.expanduser("~/Desktop/MCTP/MCTP-Bench/results"))
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()
    RESULTS_DIR = os.path.abspath(args.results)
    DB_PATH = os.path.join(RESULTS_DIR, "review.db")
    build_index(rebuild=args.rebuild)
    srv = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"review app on http://localhost:{args.port}  (results: {RESULTS_DIR})")
    srv.serve_forever()


if __name__ == "__main__":
    main()
