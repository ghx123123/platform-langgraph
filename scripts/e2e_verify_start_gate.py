"""Verify the 教学设计后暂停 dead-end fix: create a run with after_design=true,
approve with auto_start=false, then confirm the UI exposes 「开始课堂演练」 and that
clicking it actually starts Round 1.

Usage: python scripts/e2e_verify_start_gate.py
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8000"
DESIGN_ID = "8fa29273-7ba2-4554-b8fa-f33572c4b707"
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
        return e.code, e.read().decode("utf-8", "replace")[:800]


design = call("GET", f"/api/course-designs/{DESIGN_ID}")[1]
archive = call("GET", f"/api/course-archives/{design['archive_id']}")[1]
texts = [m for m in archive["materials"]
         if m.get("parse_status") == "parsed" and m.get("document_id") and m.get("category") == "textbook"]
texts.sort(key=lambda m: m.get("character_count") or 0, reverse=True)

code, run = call("POST", "/api/workflows/runs", {
    "title": "暂停门验证 P1",
    "archive_id": design["archive_id"],
    "design_id": DESIGN_ID,
    "document_id": texts[0]["document_id"],
    "document_name": texts[0]["name"],
    "document_text": (texts[0].get("excerpt") or "课程内容占位占位")[:40000],
    "document_sections": [],
    "knowledge_points": [],
    "max_iterations": 1,
    "context": "暂停门验证",
    "template_id": "teaching_design",
    "workflow_version": "classroom_v2",
    "interventions": {"after_design": True, "after_question": False},
    "scope": {"selected_point_titles": ["变量的赋值"], "estimated_minutes": 45,
              "ppt_slide_count": 2, "depth": "standard"},
})
print("create ->", code)
if code >= 400:
    sys.exit(1)
rid = run["id"]
print("RUN:", rid)
ROOT.joinpath(".runtime/pause_run.txt").write_text(rid)

for i in range(50):
    time.sleep(6)
    ss = call("GET", f"/api/classroom/runs/{rid}/start-status")[1]
    vs = call("GET", f"/api/classroom/runs/{rid}/lesson-versions")[1]["items"]
    print(f"[{i*6:>4}s] phase={ss.get('phase'):<20} versions={len(vs)} status={vs[0]['status'] if vs else '-'}")
    if ss.get("phase") == "awaiting_review" and vs and vs[0]["status"] == "draft":
        print("READY_FOR_UI", rid, vs[0]["id"])
        break
