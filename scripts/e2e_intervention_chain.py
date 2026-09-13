"""Start a classroom round and fire a 纠正/整节课 intervention while it is running,
then check the full directive -> observation -> RevisionPatch -> 复盘 chain.

Usage: python scripts/e2e_intervention_chain.py
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
    "title": "介入链路验证 P2",
    "archive_id": design["archive_id"], "design_id": DESIGN_ID,
    "document_id": texts[0]["document_id"], "document_name": texts[0]["name"],
    "document_text": (texts[0].get("excerpt") or "课程内容占位占位")[:40000],
    "document_sections": [], "knowledge_points": [], "max_iterations": 1,
    "context": "介入链路验证", "template_id": "teaching_design",
    "workflow_version": "classroom_v2",
    "interventions": {"after_design": False, "after_question": False},
    "scope": {"selected_point_titles": ["变量的赋值"], "estimated_minutes": 45,
              "ppt_slide_count": 3, "depth": "standard"},
})
if code >= 400:
    sys.exit(f"create failed {code} {run}")
rid = run["id"]
print("RUN:", rid)
ROOT.joinpath(".runtime/intervene_run.txt").write_text(rid)

call("POST", f"/api/classroom/runs/{rid}/prepare")
for _ in range(50):
    time.sleep(6)
    ss = call("GET", f"/api/classroom/runs/{rid}/start-status")[1]
    if ss.get("phase") == "awaiting_review":
        break
vid = ss.get("version_id")
print("version:", vid, ss.get("phase"))

code, res = call("POST", f"/api/classroom/runs/{rid}/lesson-versions/{vid}/approve?auto_start=true&max_rounds=1")
print("approve ->", code)

# wait until a round is running, then intervene
round_id = None
for _ in range(30):
    time.sleep(4)
    items = call("GET", f"/api/classroom/runs/{rid}/rounds")[1]["items"]
    if items and items[0]["status"] == "running":
        round_id = items[0]["id"]
        print("round running:", round_id, items[0]["current_slide_id"])
        break
if not round_id:
    sys.exit("no running round")

time.sleep(12)
for intent, scope, content in [
    ("correct", "lesson", "这个例子太难了，请换成生活化的说法重新解释赋值"),
]:
    code, res = call("POST", f"/api/classroom/runs/{rid}/rounds/{round_id}/interventions",
                     {"content": content, "intent": intent, "scope": scope})
    print(f"intervene {intent}/{scope} ->", code)
    if isinstance(res, dict):
        print("  directive:", json.dumps(res.get("directive"), ensure_ascii=False)[:300])
        print("  patches:", len(res.get("patches") or []))
        print("  teacher_event:", str((res.get("teacher_event") or {}).get("content"))[:160])
    else:
        print("  ", str(res)[:300])

for _ in range(40):
    time.sleep(6)
    items = call("GET", f"/api/classroom/runs/{rid}/rounds")[1]["items"]
    if items and items[0]["status"] in ("completed", "failed", "stopped"):
        break

print("\n=== DIRECTIVES ===")
dv = call("GET", f"/api/classroom/runs/{rid}/directives")[1]["items"]
for d in dv:
    print(" ", d["intent"], d["scope"], d["status"], "|", d["content"][:40])
print("=== PATCHES ===")
pv = call("GET", f"/api/classroom/runs/{rid}/revision-patches")[1]["items"]
for p in pv:
    print(" ", p.get("field_path"), "|", str(p.get("reason"))[:60], "| src", str(p.get("source_intervention_ids"))[:60])
print("=== OBSERVATIONS ===")
ov = call("GET", f"/api/classroom/runs/{rid}/rounds/{round_id}/observations")[1]["items"]
for o in ov:
    print(" ", o["slide_id"], o["severity"], "|", str(o.get("issue"))[:80])
    if o.get("analysis"):
        print("    analysis:", json.dumps(o["analysis"], ensure_ascii=False)[:220])
