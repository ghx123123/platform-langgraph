"""Capture zoomed-in detail screenshots for the 平台说明书.

Each shot targets a specific UI region so the document can zoom into the
功能 that matter (证据链、督导维度、教师介入、知识大纲、模板导出…).

Usage: python scripts/capture_detail_shots.py [--only key]
"""
import base64
import json
import sys
import time
import urllib.request
from pathlib import Path

CDP = "http://127.0.0.1:9333"
ROOT = Path("D:/paper/dsh/platform-langgraph")
OUT = ROOT / "docs" / "申报书" / "img"
OUT.mkdir(parents=True, exist_ok=True)
BASE = "http://127.0.0.1:5173"
RUN_ID = "e885d78a-1d22-4d38-845c-96b00566f9e2"
# 已暂停的真实会话，用于抓「介入控件可用」的截图（已完成会话控件会变灰）
LIVE_RUN = "97690342-e0e4-4073-a7cf-c30433c0b2d3"
# 含教师纠正指令链路的会话（复盘页才有「本轮教师指令」面板）
INTERVENE_RUN = "dfd6d16d-46e9-462c-a365-86a2347ac810"

from websocket import create_connection


def ws_url():
    with urllib.request.urlopen(f"{CDP}/json/list", timeout=8) as r:
        tabs = json.load(r)
    pages = [t for t in tabs if t["type"] == "page" and "5173" in t["url"]]
    return (pages or [t for t in tabs if t["type"] == "page"])[0]["webSocketDebuggerUrl"]


ws = create_connection(ws_url(), timeout=120, suppress_origin=True)
_n = [0]


def send(method, **params):
    _n[0] += 1
    mid = _n[0]
    ws.send(json.dumps({"id": mid, "method": method, "params": params}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == mid:
            if "error" in msg:
                raise RuntimeError(msg["error"])
            return msg.get("result", {})


def ev(expr):
    r = send("Runtime.evaluate", expression=expr, returnByValue=True, userGesture=True)
    if "exceptionDetails" in r:
        return None
    return r.get("result", {}).get("value")


def wait(ms):
    time.sleep(ms / 1000)


def click_js(selector_js, settle=2200):
    ok = ev(f"(()=>{{const b={selector_js};if(!b)return false;b.click();return true;}})()")
    wait(settle)
    return ok


def click_text(label, settle=2200):
    return click_js(
        "[...document.querySelectorAll('button')].find(x=>(x.innerText||'').trim()==="
        + json.dumps(label, ensure_ascii=False) + ")", settle)


def zoom(name, selector, pad=14, max_h=None, scale=2):
    """滚到元素 → 按外接矩形裁剪并放大截图。"""
    exists = ev(f"(()=>!!document.querySelector({json.dumps(selector)}))()")
    if not exists:
        print(f"  !! missing: {name} <- {selector}")
        return None
    ev(f"document.querySelector({json.dumps(selector)}).scrollIntoView({{block:'center'}})")
    wait(800)
    rect = ev(
        "(()=>{const r=document.querySelector(%s).getBoundingClientRect();"
        "return JSON.stringify({x:r.x,y:r.y,w:r.width,h:r.height});})()" % json.dumps(selector))
    d = json.loads(rect)
    vw, vh = ev("innerWidth"), ev("innerHeight")
    x = max(0, d["x"] - pad)
    y = max(0, d["y"] - pad)
    w = min(vw - x, d["w"] + pad * 2)
    h = max(80, min(vh - y, (max_h or d["h"]) + pad * 2))
    r = send("Page.captureScreenshot", format="png",
             clip={"x": x, "y": y, "width": w, "height": h, "scale": scale})
    out = OUT / f"{name}.png"
    out.write_bytes(base64.b64decode(r["data"]))
    print(f"  ok {out.name}  {round(w)}x{round(h)}")
    return out


def goto(url, settle=9000):
    send("Page.navigate", url=url)
    wait(settle)


def open_run_views():
    ev(f"localStorage.setItem('platform.classroom.run_id','{RUN_ID}');1")
    goto(BASE + "/design", settle=10000)


# ------------------------------------------------------------------ 抓图
def detail_flow():
    """七节点教学设计流水线。

    流水线在 view==='rehearsal' 时不渲染，所以先切到「本轮复盘」。
    """
    open_run_views()
    click_text("本轮复盘", settle=3500)
    zoom("D1-七节点流水线", ".classroom-flowbar", pad=10)


def detail_agents():
    """课堂演练：三维教室 + 智能体名册。"""
    open_run_views()
    click_text("课堂演练", settle=3500)
    zoom("D2-多智能体课堂全景", ".classroom-rehearsal-stage", pad=8)
    zoom("D3-课堂群聊与事件", ".classroom-chat", pad=10)


def detail_intervention():
    """教师介入面板（意图 / 范围 / 输入）。

    用已暂停的会话抓图，控件才是可用状态（已完成会话会整体变灰）。
    """
    ev(f"localStorage.setItem('platform.classroom.run_id','{LIVE_RUN}');1")
    goto(BASE + "/design", settle=10000)
    click_text("课堂演练", settle=4000)
    zoom("D4-教师介入面板", ".classroom-chat-compose", pad=8)


def detail_review():
    """督导九维度 + 逐页计划 + 逐页证据。"""
    open_run_views()
    click_text("本轮复盘", settle=3500)
    zoom("D5-督导评分维度", ".dimension-grid", pad=16)
    zoom("D6-逐页修改计划", ".review-plan-panel", pad=10, max_h=560)
    zoom("D7-逐页证据", ".review-content .review-panel:last-child", pad=10, max_h=560)
    zoom("D12-督导报告概览", ".review-score", pad=14, max_h=420)


def detail_directive():
    """教师指令面板（说了什么 / 是否被遵守 / 改了哪些地方）。

    只有教师下达过指令的会话才有这个面板；用带纠正链路的会话抓。
    """
    ev(f"localStorage.setItem('platform.classroom.run_id','{INTERVENE_RUN}');1")
    goto(BASE + "/design", settle=10000)
    click_text("本轮复盘", settle=3500)
    zoom("D8-教师指令溯源", ".review-directives", pad=10, max_h=460)


def detail_outline():
    """资料单元：知识大纲与教材范围。"""
    goto(BASE + "/materials", settle=10000)
    zoom("D9-教材知识范围与大纲", ".unit-outline, .unit-main, .material-unit-workspace", pad=6, max_h=620)


def detail_template():
    """成果中心：Word 模板与预检。"""
    goto(BASE + "/exports/lesson", settle=10000)
    zoom("D10-Word模板与预检", ".template-panel", pad=10, max_h=620)


def detail_assembly():
    """成果中心：内容编排来源列表。"""
    goto(BASE + "/exports/lesson", settle=10000)
    zoom("D11-内容编排来源", ".assembly-panel", pad=10, max_h=640)


def main():
    send("Runtime.enable")
    send("Page.enable")
    send("Emulation.setDeviceMetricsOverride", width=1600, height=1000,
         deviceScaleFactor=2, mobile=False)
    steps = [
        ("flow", detail_flow),
        ("agents", detail_agents),
        ("intervene", detail_intervention),
        ("score", lambda: (open_run_views(), click_text("本轮复盘", settle=3500),
                           zoom("D5-督导评分维度", ".dimension-grid", pad=16),
                           zoom("D12-督导报告概览", ".review-score", pad=14, max_h=420))[-1]),
        ("plan", lambda: (open_run_views(), click_text("本轮复盘", settle=3500),
                          zoom("D6-逐页修改计划", ".review-plan-panel", pad=10, max_h=560))[-1]),
        ("evidence", lambda: (open_run_views(), click_text("本轮复盘", settle=3500),
                              zoom("D7-逐页证据", ".review-content .review-panel:last-child", pad=10, max_h=560))[-1]),
        ("directive", detail_directive),
        ("outline", detail_outline),
        ("template", detail_template),
        ("assembly", detail_assembly),
    ]
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    for key, fn in steps:
        if only and key != only:
            continue
        print(f"[{key}]")
        try:
            fn()
        except Exception as exc:
            print(f"  !! {key}: {exc}")
    print("done")


if __name__ == "__main__":
    main()
