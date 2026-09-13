"""Reproduce the frontend's PPT-approve (auto_start=true) path and run a full classroom round.

Usage: python scripts/e2e_classroom_round.py
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8000"
ROOT = Path("D:/paper/dsh/platform-langgraph")


def call(method, path, body=None, timeout=180):
    data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(raw) if raw.strip().startswith(("{", "[")) else raw)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:1200]


def start_status(rid):
    _, d = call("GET", f"/api/classroom/runs/{rid}/start-status")
    return d if isinstance(d, dict) else {}


rid = sys.argv[1] if len(sys.argv) > 1 else ROOT.joinpath(".runtime/e2e_ui_run.txt").read_text().strip()
print("RUN:", rid)

# 1. ensure blueprint exists
ss = start_status(rid)
if ss.get("phase") in ("idle", "queued") or not ss.get("version_id"):
    print("prepare ->", call("POST", f"/api/classroom/runs/{rid}/prepare")[0])
    for _ in range(40):
        time.sleep(6)
        ss = start_status(rid)
        print("  phase", ss.get("phase"), ss.get("generated_chars"))
        if ss.get("phase") == "awaiting_review":
            break

vid = ss.get("version_id")
print("version:", vid, ss.get("phase"))

# 2. approve with auto_start=true (what the UI does when 教学设计后暂停 is unchecked)
code, res = call("POST", f"/api/classroom/runs/{rid}/lesson-versions/{vid}/approve?auto_start=true&max_rounds=1")
print("approve auto_start=true ->", code, json.dumps(res, ensure_ascii=False)[:500] if isinstance(res, dict) else res)

# 3. watch the round
for i in range(30):
    time.sleep(8)
    code, rounds = call("GET", f"/api/classroom/runs/{rid}/rounds")
    items = rounds.get("items", []) if isinstance(rounds, dict) else []
    ss = start_status(rid)
    print(f"[{i*8:>4}s] phase={ss.get('phase')} rounds={[(r['round_number'], r['status'], r['current_slide_id']) for r in items]}")
    if items and items[0]["status"] in ("completed", "failed", "stopped"):
        break

# 4. dump events + report
rid_round = items[0]["id"] if items else None
if rid_round:
    for p in (f"/api/classroom/runs/{rid}/rounds/{rid_round}/report",
              f"/api/classroom/runs/{rid}/rounds/{rid_round}/observations"):
        code, d = call("GET", p)
        print("==", p, code)
        print(json.dumps(d, ensure_ascii=False)[:1200])
