"""Create a cleanly-titled python course run for documentation screenshots.

Usage: python scripts/make_doc_run.py
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8000"
DESIGN_ID = "8fa29273-7ba2-4554-b8fa-f33572c4b707"
ROOT = Path("D:/paper/dsh/platform-langgraph")
TITLE = "Python 程序设计基础与应用 · 第 1 章 Python 概述"


def call(method, path, body=None, timeout=240):
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
ch1 = next((m for m in texts if "01" in (m.get("name") or "")), texts[0])
print("教材:", ch1["name"][:60], ch1.get("character_count"))

code, run = call("POST", "/api/workflows/runs", {
    "title": TITLE,
    "archive_id": design["archive_id"],
    "design_id": DESIGN_ID,
    "document_id": ch1["document_id"],
    "document_name": ch1["name"],
    "document_text": (ch1.get("excerpt") or "Python 概述课程内容")[:60000],
    "document_sections": [],
    "knowledge_points": [],
    "max_iterations": 1,
    "context": "面向本科一年级学生的 Python 程序设计入门课，第 1 章 Python 概述。",
    "template_id": "teaching_design",
    "workflow_version": "classroom_v2",
    "interventions": {"after_design": False, "after_question": False},
    "scope": {"selected_point_titles": ["Python 语言简介", "Python 版本简介", "Python 开发环境安装与配置"],
              "estimated_minutes": 45, "ppt_slide_count": 3, "depth": "standard"},
})
print("create ->", code)
if code >= 400:
    sys.exit(str(run))
rid = run["id"]
print("RUN:", rid)
ROOT.joinpath(".runtime/doc_run.txt").write_text(rid)

call("POST", f"/api/classroom/runs/{rid}/prepare")
for i in range(60):
    time.sleep(6)
    ss = call("GET", f"/api/classroom/runs/{rid}/start-status")[1]
    print(f"[{i*6:>4}s] {ss.get('phase')} chars={ss.get('generated_chars')}")
    if ss.get("phase") == "awaiting_review":
        break
vid = ss.get("version_id")
code, res = call("POST", f"/api/classroom/runs/{rid}/lesson-versions/{vid}/approve?auto_start=true&max_rounds=1")
print("approve ->", code)
for i in range(60):
    time.sleep(8)
    rounds = call("GET", f"/api/classroom/runs/{rid}/rounds")[1]["items"]
    if rounds and rounds[0]["status"] in ("completed", "failed", "stopped"):
        print("round:", rounds[0]["status"])
        break
    if rounds:
        print(f"[{i*8:>4}s] round {rounds[0]['status']} slide={rounds[0]['current_slide_id']}")
print("DONE", rid)
