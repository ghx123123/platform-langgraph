"""Capture document screenshots for the platform 说明书 (python course walkthrough).

Drives the real UI over CDP and saves titled PNGs into docs/申报书/img/.

Usage: python scripts/capture_doc_shots.py [--only N]
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

# 默认停在「暂停门验证」run（python 课程、已完成、有完整课堂+复盘数据）
RUN_ID = "e885d78a-1d22-4d38-845c-96b00566f9e2"
# 有督导评分 83 且含纠正类介入链路的 run
RUN_INTERVENE = "dfd6d16d-46e9-462c-a365-86a2347ac810"


def ws_url():
    with urllib.request.urlopen(f"{CDP}/json/list", timeout=8) as r:
        tabs = json.load(r)
    pages = [t for t in tabs if t["type"] == "page" and "5173" in t["url"]]
    return (pages or [t for t in tabs if t["type"] == "page"])[0]["webSocketDebuggerUrl"]


from websocket import create_connection

ws = create_connection(ws_url(), timeout=120, suppress_origin=True)
_i = [0]


def send(method, **params):
    _i[0] += 1
    mid = _i[0]
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


def click_text(label, exact=False, settle=1800):
    js = (
        "(()=>{const vis=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0;};"
        "for(const e of document.querySelectorAll('button,a,[role=button],.classroom-tabs button')){"
        "if(!vis(e)||e.disabled)continue;const s=(e.innerText||'').trim();if(%s){"
        "const r=e.getBoundingClientRect();return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2,t:s.slice(0,30)});}}return null;})()"
        % ("s === " + json.dumps(label, ensure_ascii=False) if exact
           else "s.includes(" + json.dumps(label, ensure_ascii=False) + ")")
    )
    v = ev(js)
    if not v:
        return None
    d = json.loads(v)
    for e in ("mousePressed", "mouseReleased"):
        send("Input.dispatchMouseEvent", type=e, x=d["x"], y=d["y"], button="left", clickCount=1)
    wait(settle)
    return d


def shot(name, full=True):
    """Capture the viewport; full=True measures the tallest scroll container."""
    if full:
        ev("(()=>{const els=[...document.querySelectorAll('*')].filter(e=>e.scrollHeight>e.clientHeight+60&&e.clientHeight>300);"
           "els.sort((a,b)=>b.scrollHeight-a.scrollHeight);if(els[0])els[0].scrollTop=0;return 1;})()")
        wait(700)
    r = send("Page.captureScreenshot", format="png", captureBeyondViewport=False)
    p = OUT / f"{name}.png"
    p.write_bytes(base64.b64decode(r["data"]))
    print("  shot:", p.name)
    return p


def goto(url, settle=9000):
    send("Page.navigate", url=url)
    wait(settle)


def set_run(run_id):
    ev(f"localStorage.setItem('platform.classroom.run_id','{run_id}');1")


def scroll_main(frac):
    return ev(
        "(()=>{const els=[...document.querySelectorAll('*')].filter(e=>e.scrollHeight>e.clientHeight+60&&e.clientHeight>300);"
        "els.sort((a,b)=>b.scrollHeight-a.scrollHeight);const el=els[0];if(!el)return null;"
        f"el.scrollTop=el.scrollHeight*{frac};return Math.round(el.scrollTop)+'/'+el.scrollHeight;}})()"
    )


def zoom(name, selector, pad=12, min_h=140, scroll=True):
    """对某个局部元素做放大截图（说明书用的细节图）。

    先把元素滚到视口内，再按元素外接矩形加内边距裁剪截图。
    """
    rect = ev(
        "(()=>{const e=document.querySelector(%s);if(!e)return null;"
        "if(%s)e.scrollIntoView({block:'center'});"
        "const r=e.getBoundingClientRect();"
        "return JSON.stringify({x:r.x,y:r.y,w:r.width,h:r.height});})()"
        % (json.dumps(selector), "true" if scroll else "false")
    )
    if not rect:
        print("  !! zoom miss:", selector)
        return None
    wait(900)
    rect = ev(
        "(()=>{const e=document.querySelector(%s);const r=e.getBoundingClientRect();"
        "return JSON.stringify({x:r.x,y:r.y,w:r.width,h:r.height});})()" % json.dumps(selector)
    )
    d = json.loads(rect)
    vw = ev("innerWidth"); vh = ev("innerHeight")
    x = max(0, d["x"] - pad)
    y = max(0, d["y"] - pad)
    w = min(vw - x, d["w"] + pad * 2)
    h = min(vh - y, max(d["h"], min_h) + pad * 2)
    r = send("Page.captureScreenshot", format="png",
             clip={"x": x, "y": y, "width": w, "height": h, "scale": 2})
    out = OUT / f"{name}.png"
    out.write_bytes(base64.b64decode(r["data"]))
    print(f"  zoom: {out.name} ({round(w)}x{round(h)})")
    return out


# ---------------------------------------------------------------- 页面清单
def cap_overview():
    goto(BASE + "/")
    shot("01-中台总览")


def cap_hub():
    click_text("课程资料库")
    shot("02-课程资料库")


def cap_material_unit():
    click_text("资料单元", settle=4000)
    shot("03-资料单元")


def cap_design_workspace():
    """已完成会话默认落在「课堂演练」；说明书要的是三栏备课工作台，
    所以显式切回「材料预览」。"""
    set_run(RUN_ID)
    goto(BASE + "/design", settle=10000)
    # 外层工作区 tab（材料预览/生成过程/教学成果）在 .workspace-tabs 里，
    # 点它才能看到「材料预览」视图；内层 classroom tab 同名会误命中。
    ev("""(()=>{const b=[...document.querySelectorAll('.workspace-tabs button')]
        .find(x=>(x.innerText||'').includes('材料预览'));if(b)b.click();return !!b;})()""")
    wait(3000)
    shot("04-课程设计工作台")


def cap_preparation():
    click_text("生成过程")
    wait(2000)
    shot("05-生成过程")


def cap_ppt_review():
    click_text("PPT 审阅")
    shot("06-PPT审阅")


def cap_classroom():
    click_text("课堂演练", settle=3000)
    shot("07-课堂演练")


def cap_review():
    click_text("本轮复盘", settle=3000)
    shot("08-本轮复盘")
    scroll_main("0.45")
    wait(900)
    shot("09-本轮复盘-下")


def cap_versions():
    click_text("版本对比", settle=2500)
    shot("10-版本对比")


def cap_debug():
    click_text("Agent 调试", settle=2500)
    shot("11-Agent调试")


def cap_exports():
    goto(BASE + "/exports/lesson", settle=9000)
    shot("12-成果中心-教案定稿")


def cap_exports_compose():
    goto(BASE + "/exports/compose", settle=9000)
    shot("13-成果中心-内容编排")


def main():
    send("Runtime.enable")
    send("Page.enable")
    send("Emulation.setDeviceMetricsOverride", width=1600, height=1000,
         deviceScaleFactor=2, mobile=False)
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]

    steps = [
        ("overview", cap_overview),
        ("hub", cap_hub),
        ("unit", cap_material_unit),
        ("design", cap_design_workspace),
        ("prep", cap_preparation),
        ("ppt", cap_ppt_review),
        ("classroom", cap_classroom),
        ("review", cap_review),
        ("versions", cap_versions),
        ("debug", cap_debug),
        ("exports", cap_exports),
        ("compose", cap_exports_compose),
    ]
    for key, fn in steps:
        if only and key != only:
            continue
        print(f"[{key}]")
        try:
            fn()
        except Exception as exc:
            print(f"  !! {key} failed: {exc}")
    print("done ->", OUT)


if __name__ == "__main__":
    main()
