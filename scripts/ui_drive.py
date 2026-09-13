"""Browser test driver for the 课程设计 flow (CDP based, no MCP browser server needed).

Usage:
  python scripts/ui_drive.py <cmd> [args]

Commands:
  snap [name]                 screenshot to screenshots/ui/<name>.png
  text [n]                    visible page text
  els [--all]                 list visible interactive elements with selectors + rects
  click "<label>"             click first visible element whose text matches
  click-index <i>             click element #i from last `els` listing
  sel "<css>" <action>        action = click|text|value|attr
  fill "<css>" "<value>"      set input value (React-friendly)
  api GET|POST|PUT|DELETE <path> [json]   call backend, print status+body
  console                     dump captured console messages
  net                         dump captured network requests
  errors                      dump page errors
  wait <ms>
  eval "<js>"
  url <url>
"""
import base64
import json
import sys
import time
import urllib.request
from pathlib import Path

CDP = "http://127.0.0.1:9333"
ROOT = Path("D:/paper/dsh/platform-langgraph")
OUT = ROOT / "screenshots" / "ui"
OUT.mkdir(parents=True, exist_ok=True)
LAST_ELS = ROOT / ".runtime" / "ui_last_els.json"


def ws_url():
    with urllib.request.urlopen(f"{CDP}/json/list", timeout=8) as r:
        tabs = json.load(r)
    pages = [t for t in tabs if t["type"] == "page" and "5173" in t["url"]]
    if not pages:
        pages = [t for t in tabs if t["type"] == "page"]
    if not pages:
        raise SystemExit("no page tab")
    return pages[0]["webSocketDebuggerUrl"]


class Conn:
    def __init__(self):
        from websocket import create_connection
        self.events = []
        try:
            self.ws = create_connection(ws_url(), timeout=60, suppress_origin=True)
        except TypeError:
            self.ws = create_connection(ws_url(), timeout=60)
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
            self.events.append(msg)

    def drain(self, seconds=0.4):
        """Collect async events for a while."""
        self.ws.settimeout(seconds)
        try:
            while True:
                msg = json.loads(self.ws.recv())
                self.events.append(msg)
        except Exception:
            pass
        self.ws.settimeout(60)

    def enable(self):
        self.send("Runtime.enable")
        self.send("Page.enable")
        self.send("Log.enable")
        self.send("Network.enable")

    def eval(self, expr, await_promise=True):
        r = self.send("Runtime.evaluate", expression=expr, returnByValue=True,
                      awaitPromise=await_promise, userGesture=True)
        if "exceptionDetails" in r:
            return {"__error__": str(r["exceptionDetails"])[:800]}
        return r.get("result", {}).get("value")

    def click_xy(self, x, y):
        for t in ("mousePressed", "mouseReleased"):
            self.send("Input.dispatchMouseEvent", type=t, x=x, y=y, button="left", clickCount=1)

    def shot(self, name):
        r = self.send("Page.captureScreenshot", format="png")
        p = OUT / (name if name.endswith(".png") else name + ".png")
        p.write_bytes(base64.b64decode(r["data"]))
        return str(p)


HELPERS = r"""
window.__ui = {
  vis(el) {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    const s = getComputedStyle(el);
    if (s.visibility === 'hidden' || s.display === 'none' || s.opacity === '0') return false;
    if (r.bottom < 0 || r.top > innerHeight + 200) return false;
    return true;
  },
  css(el) {
    if (!el || el.nodeType !== 1) return '';
    if (el.id) return '#' + el.id;
    const parts = [];
    let cur = el, depth = 0;
    while (cur && cur.nodeType === 1 && depth < 4) {
      let p = cur.tagName.toLowerCase();
      if (cur.classList.length) p += '.' + [...cur.classList].slice(0,2).join('.');
      parts.unshift(p);
      cur = cur.parentElement; depth++;
    }
    return parts.join(' > ');
  },
  label(el) {
    return (el.innerText || el.getAttribute('aria-label') || el.placeholder || el.value || el.title || '').trim().replace(/\s+/g,' ').slice(0,80);
  },
  list() {
    const sel = 'button,a,[role=button],input,select,textarea,[onclick],summary';
    const out = [];
    for (const e of document.querySelectorAll(sel)) {
      if (!window.__ui.vis(e)) continue;
      const r = e.getBoundingClientRect();
      out.push({i: out.length, tag: e.tagName, type: e.getAttribute('type')||'',
                label: window.__ui.label(e), sel: window.__ui.css(e),
                disabled: !!e.disabled,
                x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                w: Math.round(r.width), h: Math.round(r.height)});
    }
    return out;
  },
  clickText(t) {
    const sel = 'button,a,[role=button],summary,li,div[class*=card],td';
    for (const e of document.querySelectorAll(sel)) {
      if (!window.__ui.vis(e)) continue;
      if (window.__ui.label(e).includes(t)) {
        const r = e.getBoundingClientRect();
        return {x: r.x + r.width/2, y: r.y + r.height/2, label: window.__ui.label(e)};
      }
    }
    return null;
  }
};
'ok'
"""


def react_fill_js(sel, value):
    return """
    (() => {
      const el = document.querySelector(%s);
      if (!el) return 'NOT_FOUND';
      const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype
                   : el.tagName === 'SELECT'   ? HTMLSelectElement.prototype
                   : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
      setter.call(el, %s);
      el.dispatchEvent(new Event('input', {bubbles: true}));
      el.dispatchEvent(new Event('change', {bubbles: true}));
      return 'ok:' + el.value.slice(0, 60);
    })()
    """ % (json.dumps(sel), json.dumps(value))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    c = Conn()
    c.enable()
    c.eval(HELPERS)
    cmd = sys.argv[1]

    if cmd == "snap":
        c.drain(0.3)
        print(c.shot(sys.argv[2] if len(sys.argv) > 2 else "snap"))
    elif cmd == "text":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 3000
        print(c.eval(f"document.body.innerText.slice(0,{n})"))
    elif cmd == "els":
        c.eval(HELPERS)
        els = c.eval("window.__ui.list()", await_promise=False)
        LAST_ELS.write_text(json.dumps(els, ensure_ascii=False), encoding="utf-8")
        for e in els:
            mark = " [DISABLED]" if e["disabled"] else ""
            print(f"#{e['i']:>3} {e['tag']:<9}{e['type']:<8} ({e['x']:>5},{e['y']:>5}) {e['label']}{mark}")
    elif cmd == "click":
        label = sys.argv[2]
        c.eval(HELPERS)
        d = c.eval("window.__ui.clickText(%s)" % json.dumps(label, ensure_ascii=False), await_promise=False)
        if not d:
            print("NOT_FOUND:", label)
            return
        c.click_xy(d["x"], d["y"])
        print("clicked:", d["label"])
    elif cmd == "click-index":
        idx = int(sys.argv[2])
        els = json.loads(LAST_ELS.read_text(encoding="utf-8"))
        e = els[idx]
        c.click_xy(e["x"], e["y"])
        print("clicked:", e["label"])
    elif cmd == "fill":
        print(c.eval(react_fill_js(sys.argv[2], sys.argv[3])))
    elif cmd == "eval":
        print(json.dumps(c.eval(sys.argv[2]), ensure_ascii=False, indent=1))
    elif cmd == "wait":
        time.sleep(int(sys.argv[2]) / 1000)
        print("waited", sys.argv[2])
    elif cmd == "url":
        c.send("Page.navigate", url=sys.argv[2])
        time.sleep(4)
        print("navigated")
    elif cmd == "api":
        method, path = sys.argv[2], sys.argv[3]
        body = sys.argv[4].encode() if len(sys.argv) > 4 else None
        req = urllib.request.Request("http://127.0.0.1:8000" + path, data=body, method=method)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                print(r.status, r.read().decode("utf-8", "replace")[:3000])
        except urllib.error.HTTPError as e:
            print(e.code, e.read().decode("utf-8", "replace")[:2000])
    elif cmd in ("console", "net", "errors"):
        c.drain(1.0)
        out = []
        for m in c.events:
            meth = m.get("method", "")
            p = m.get("params", {})
            if meth == "Runtime.consoleAPICalled":
                out.append({"t": p.get("type"), "args": [(a.get("value") if "value" in a else a.get("description", "")) for a in p.get("args", [])]})
            elif meth == "Runtime.exceptionThrown":
                out.append({"EXCEPTION": (p.get("exceptionDetails", {}).get("exception", {}) or {}).get("description", "")[:400]})
            elif meth == "Log.entryAdded":
                e = p.get("entry", {})
                out.append({"LOG": e.get("level"), "text": e.get("text", "")[:300]})
            elif meth == "Network.responseReceived":
                r0 = p.get("response", {})
                if r0.get("status", 0) >= 400 or "/api/" in r0.get("url", ""):
                    out.append({"NET": r0.get("status"), "url": r0.get("url", "")[:140]})
            elif meth == "Network.loadingFailed":
                out.append({"NETFAIL": p.get("errorText"), "rid": p.get("requestId")})
        for o in out[-60:]:
            print(json.dumps(o, ensure_ascii=False))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
