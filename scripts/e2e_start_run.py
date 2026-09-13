"""Start a real classroom_v2 run end-to-end on the existing python archive.

Usage: python scripts/e2e_start_run.py [title]
Prints the created run id and then tails status for a while.
"""
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8000"
DESIGN_ID = "8fa29273-7ba2-4554-b8fa-f33572c4b707"
TITLE = sys.argv[1] if len(sys.argv) > 1 else "E2E 课程设计流程验证"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return json.load(r)


def post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:1500]


design = get(f"/api/course-designs/{DESIGN_ID}")
archive = get(f"/api/course-archives/{design['archive_id']}")
texts = [
    m for m in archive.get("materials", [])
    if m.get("parse_status") == "parsed" and m.get("document_id") and m.get("category") == "textbook"
]
texts.sort(key=lambda m: m.get("character_count") or 0, reverse=True)
print("parsed textbook materials:", [(m["name"][:40], m["character_count"]) for m in texts[:5]])

excerpt = (texts[0].get("excerpt") or "") if texts else ""
if len(excerpt) < 10:
    excerpt = ("第1章 Python概述。本讲介绍变量的概念：变量是内存中数据的名字，"
               "赋值语句 x = 10 先计算右侧表达式的值，再把结果存进左边的变量名；"
               "同一变量名可以重复赋值，新值会覆盖旧值。变量命名需遵循标识符规则："
               "由字母、数字、下划线组成，不能以数字开头，区分大小写，不能使用关键字。")

body = {
    "title": TITLE,
    "archive_id": design["archive_id"],
    "design_id": DESIGN_ID,
    "document_id": texts[0].get("document_id") if texts else None,
    "document_name": texts[0]["name"] if texts else "python 教材",
    "document_text": excerpt[:60000],
    "document_sections": [],
    "knowledge_points": [],
    "max_iterations": 1,
    "context": "端到端流程验证：第1章变量与赋值",
    "template_id": "teaching_design",
    "workflow_version": "classroom_v2",
    "interventions": {"after_design": True, "after_question": False},
    "scope": {
        "selected_point_titles": ["变量的赋值", "变量命名规则"],
        "estimated_minutes": 45,
        "ppt_slide_count": 3,
        "depth": "standard",
    },
}
status, run = post("/api/workflows/runs", body)
print("POST /workflows/runs ->", status)
print(json.dumps(run, ensure_ascii=False)[:900])
if status >= 400:
    sys.exit(1)

run_id = run["id"]
print("RUN_ID:", run_id)
open("D:/paper/dsh/platform-langgraph/.runtime/e2e_run_id.txt", "w").write(run_id)

for i in range(40):
    time.sleep(6)
    try:
        r = get(f"/api/workflows/runs/{run_id}")
        ev = get(f"/api/workflows/runs/{run_id}/events?limit=200")
    except Exception as exc:
        print(i, "poll error", exc)
        continue
    items = ev.get("items", [])
    last = items[-1] if items else {}
    print(f"[{i*6:>4}s] status={r.get('status')} phase={r.get('current_phase')} events={len(items)} last={last.get('type')}")
    if r.get("status") in ("completed", "failed", "cancelled", "paused", "waiting"):
        print("FINAL:", r.get("status"), r.get("current_phase"), r.get("error"))
        break
