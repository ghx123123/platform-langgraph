"""Verify high-risk claims directly against the repo source (no UI needed)."""
import json
import re
from pathlib import Path

ROOT = Path("D:/paper/dsh/platform-langgraph")
out = {}


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def has(rel, pat, regex=False):
    src = read(rel)
    if regex:
        return bool(re.search(pat, src))
    return pat in src


# --- H2: is classroom start ever called from the frontend?
hits = []
for p in (ROOT / "frontend" / "src").rglob("*.ts*"):
    s = p.read_text(encoding="utf-8", errors="replace")
    if "classroomApi.start(" in s:
        hits.append(str(p.relative_to(ROOT)))
out["H2_classroom_start_callers"] = hits
out["H2_start_defined_in_api"] = has("frontend/src/lib/api.ts", "start: (runId")

# --- H9: is detailPanelOpen ever set true?
app = read("frontend/src/App.tsx")
out["H9_setDetailPanelOpen_true"] = re.findall(r"setDetailPanelOpen\(([^)]*)\)", app)

# --- H10: AgentFlowWorkspace importers
importers = []
for p in (ROOT / "frontend" / "src").rglob("*.tsx"):
    if p.name == "AgentFlowWorkspace.tsx":
        continue
    s = p.read_text(encoding="utf-8", errors="replace")
    if "AgentFlowWorkspace" in s:
        importers.append(str(p.relative_to(ROOT)))
out["H10_AgentFlowWorkspace_importers"] = importers

# --- legacy components still mounted?
for comp in ["InterventionPanel", "phases", "groupByIteration"]:
    out[f"legacy_{comp}"] = re.findall(rf"\b{comp}\b", app)[:6]

# --- H5: createSession without design
out["H5_createSession_archive_id"] = "archive_id: activeDesign?.archive_id" in app

# --- H6: 教学成果 disabled condition
m = re.search(r"教学成果[\s\S]{0,400}?disabled=\{([^}]*)\}", app)
out["H6_result_tab_disabled"] = m.group(1) if m else None

# --- classroom module: which fields exist in models
cm = read("backend/classroom/models.py")
out["classroom_model_classes"] = re.findall(r"^class (\w+)", cm, re.M)

# --- RevisionPatch produced anywhere?
out["revision_patch_refs"] = {f: len(re.findall("RevisionPatch", read(f)))
                              for f in ["backend/classroom/revision.py", "backend/classroom/orchestrator.py",
                                        "backend/classroom/integration.py"]}

# --- apply_patches
out["apply_patches_def"] = re.findall(r"def apply_patches[\s\S]{0,200}", read("backend/classroom/repository.py"))[:1]

# --- 教学成果 / ResultPanel needs final_output
out["final_output_refs_app"] = len(re.findall("final_output", app))

print(json.dumps(out, ensure_ascii=False, indent=1))
(ROOT / ".runtime" / "static_verify.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
