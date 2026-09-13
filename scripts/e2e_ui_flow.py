"""Full classroom_v2 E2E via UI: create run (interventions off), watch auto-prepare,
approve PPT from the browser, then start classroom from the browser if the UI offers it.

Usage: python scripts/e2e_ui_flow.py
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8000"
DESIGN_ID = "8fa29273-7ba2-4554-b8fa-f33572c4b707"
ROOT = Path("D:/paper/dsh/platform-langgraph")


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def post(path, body=None):
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request(BASE + path, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:800]


design = get(f"/api/course-designs/{DESIGN_ID}")
archive = get(f"/api/course-archives/{design['archive_id']}")
texts = [m for m in archive["materials"]
         if m.get("parse_status") == "parsed" and m.get("document_id") and m.get("category") == "textbook"]
texts.sort(key=lambda m: m.get("character_count") or 0, reverse=True)

status, run = post("/api/workflows/runs", {
    "title": "E2E 自动流程验证",
    "archive_id": design["archive_id"],
    "design_id": DESIGN_ID,
    "document_id": texts[0]["document_id"],
    "document_name": texts[0]["name"],
    "document_text": (texts[0].get("excerpt") or "课程内容占位")[:60000],
    "document_sections": [],
    "knowledge_points": [],
    "max_iterations": 1,
    "context": "自动流程验证",
    "template_id": "teaching_design",
    "workflow_version": "classroom_v2",
    "interventions": {"after_design": False, "after_question": False},
    "scope": {"selected_point_titles": ["变量的赋值"], "estimated_minutes": 45,
              "ppt_slide_count": 2, "depth": "standard"},
})
print("create run ->", status)
if status >= 400:
    sys.exit(1)
rid = run["id"]
print("RUN:", rid)
ROOT.joinpath(".runtime/e2e_ui_run.txt").write_text(rid)

# wait for the frontend to auto-prepare (ClassroomWorkspace autoPrepareRunRef) or drive it
for i in range(60):
    time.sleep(6)
    ss = get(f"/api/classroom/runs/{rid}/start-status")
    vs = get(f"/api/classroom/runs/{rid}/lesson-versions")["items"]
    print(f"[{i*6:>4}s] phase={ss['phase']:<22} chars={ss['generated_chars']:<6} versions={len(vs)} "
          f"status={vs[0]['status'] if vs else '-'}")
    if ss["phase"] == "awaiting_review" and vs and vs[0]["status"] == "draft":
        print("READY_FOR_UI_APPROVE", rid)
        break
    if ss["phase"] in ("failed", "classroom_running", "classroom_completed"):
        print("PHASE:", ss["phase"], ss["message"])
        break
