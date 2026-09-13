"""CDP 浏览器驱动助手 — 连接已在 9222 端口开启调试的 Chrome, 供会话内交互分析使用。

用法:
  python scripts/cdp.py shot [name]            # 截图
  python scripts/cdp.py text [n]               # 页面可见文本前 n 字
  python scripts/cdp.py buttons                # 列出所有可见按钮/可点元素
  python scripts/cdp.py click "文本"            # 按可见文本点击
  python scripts/cdp.py click-sel "css选择器"   # 按选择器点击
  python scripts/cdp.py eval "<js>"            # 执行 JS 并打印结果
  python scripts/cdp.py url "<url>"            # 导航
"""
import json, sys, time, base64, urllib.request
from pathlib import Path

OUT = Path("D:/paper/dsh/platform-langgraph/screenshots")
OUT.mkdir(parents=True, exist_ok=True)
CDP = "http://127.0.0.1:9222"


def ws_url():
    with urllib.request.urlopen(f"{CDP}/json/list", timeout=5) as r:
        tabs = json.load(r)
    for t in tabs:
        if t["type"] == "page" and "127.0.0.1:5173" in t["url"]:
            return t["webSocketDebuggerUrl"]
    for t in tabs:
        if t["type"] == "page":
            return t["webSocketDebuggerUrl"]
    raise SystemExit("no page tab found")


class Conn:
    def __init__(self):
        from websocket import create_connection  # websocket-client
        try:
            self.ws = create_connection(ws_url(), timeout=30, suppress_origin=True)
        except TypeError:
            self.ws = create_connection(ws_url(), timeout=30)
        self.i = 0

    def send(self, method, **params):
        self.i += 1
        mid = self.i
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    def eval(self, expr, await_promise=False):
        r = self.send("Runtime.evaluate", expression=expr, returnByValue=True,
                      awaitPromise=await_promise, userGesture=True)
        if "exceptionDetails" in r:
            return {"error": str(r["exceptionDetails"])[:500]}
        return r.get("result", {}).get("value")

    def shot(self, name):
        r = self.send("Page.captureScreenshot", format="png")
        p = OUT / (name if name.endswith(".png") else name + ".png")
        p.write_bytes(base64.b64decode(r["data"]))
        return str(p)

    def click_xy(self, x, y):
        for t in ("mousePressed", "mouseReleased"):
            self.send("Input.dispatchMouseEvent", type=t, x=x, y=y, button="left",
                      clickCount=1)

    def type_text(self, text):
        for ch in text:
            self.send("Input.dispatchKeyEvent", type="char", text=ch)

    def goto(self, url):
        self.send("Page.navigate", url=url)
        time.sleep(3)


HELPERS_JS = r"""
window.__cdp = {
  visible(el) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return false;
    const s = getComputedStyle(el);
    return s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0';
  },
  byText(txt, tag) {
    const sel = tag || 'button,a,[role=button],.tab,li,div[class*=card]';
    const all = [...document.querySelectorAll(sel)];
    return all.filter(e => __cdp.visible(e) && e.innerText && e.innerText.trim().includes(txt));
  },
  rect(el) { const r = el.getBoundingClientRect(); return {x:r.x+r.width/2, y:r.y+r.height/2, w:r.width, h:r.height}; }
};
"""


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd = sys.argv[1]
    c = Conn()
    c.send("Runtime.enable")
    c.send("Page.enable")
    c.eval(HELPERS_JS)

    if cmd == "shot":
        print(c.shot(sys.argv[2] if len(sys.argv) > 2 else "cdp-shot"))
    elif cmd == "text":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 2500
        print(c.eval(f"document.body.innerText.slice(0,{n})"))
    elif cmd == "buttons":
        js = (
            "(() => { const out = [];"
            " for (const e of document.querySelectorAll('button,a,[role=button],input,select,textarea')) {"
            "   if (!__cdp.visible(e)) continue;"
            "   const r = e.getBoundingClientRect();"
            "   out.push({tag:e.tagName, text:(e.innerText||e.placeholder||e.value||'').trim().slice(0,50),"
            "             cls:(e.className||'').toString().slice(0,60),"
            "             x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)});"
            " } return out; })()"
        )
        print(json.dumps(c.eval(js), ensure_ascii=False, indent=1))
    elif cmd == "click":
        txt = sys.argv[2]
        res = c.eval(rf"""
          (() => {{
            const els = __cdp.byText({json.dumps(txt, ensure_ascii=False)});
            if (!els.length) return 'NOT_FOUND';
            const e = els[0];
            const r = e.getBoundingClientRect();
            return JSON.stringify({{x: r.x + r.width/2, y: r.y + r.height/2, text: e.innerText.trim().slice(0,60)}});
          }})()
        """)
        if res == "NOT_FOUND":
            print("NOT_FOUND:", txt); return
        d = json.loads(res)
        c.click_xy(d["x"], d["y"])
        print("clicked:", d["text"], "at", round(d["x"]), round(d["y"]))
    elif cmd == "click-sel":
        sel = sys.argv[2]
        res = c.eval(rf"""
          (() => {{
            const e = document.querySelector({json.dumps(sel)});
            if (!e) return 'NOT_FOUND';
            const r = e.getBoundingClientRect();
            return JSON.stringify({{x: r.x + r.width/2, y: r.y + r.height/2, text: (e.innerText||'').trim().slice(0,60)}});
          }})()
        """)
        if res == "NOT_FOUND":
            print("NOT_FOUND:", sel); return
        d = json.loads(res)
        c.click_xy(d["x"], d["y"])
        print("clicked:", d["text"], "at", round(d["x"]), round(d["y"]))
    elif cmd == "eval":
        print(json.dumps(c.eval(sys.argv[2], await_promise=True), ensure_ascii=False, indent=1))
    elif cmd == "url":
        c.goto(sys.argv[2]); print("navigated:", sys.argv[2])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
