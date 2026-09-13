"""Click a labeled control and capture the resulting network activity + console errors.

Usage: python scripts/ui_watch_click.py "<button text>" [settle_ms]
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


def ws_url():
    with urllib.request.urlopen(f"{CDP}/json/list", timeout=8) as r:
        tabs = json.load(r)
    pages = [t for t in tabs if t["type"] == "page" and "5173" in t["url"]]
    return (pages or [t for t in tabs if t["type"] == "page"])[0]["webSocketDebuggerUrl"]


from websocket import create_connection

ws = create_connection(ws_url(), timeout=60, suppress_origin=True)
ctr = [0]


def send(method, **params):
    ctr[0] += 1
    mid = ctr[0]
    ws.send(json.dumps({"id": mid, "method": method, "params": params}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == mid:
            if "error" in msg:
                raise RuntimeError(msg["error"])
            return msg.get("result", {})


send("Runtime.enable")
send("Page.enable")
send("Network.enable")

label = sys.argv[1]
settle = int(sys.argv[2]) if len(sys.argv) > 2 else 12000

# pre-click state
pre = send("Runtime.evaluate", expression="JSON.stringify({url:location.href,ls:localStorage.getItem('platform.classroom.run_id')})",
           returnByValue=True).get("result", {}).get("value")
print("PRE:", pre)


def click_by_text(t):
    js = """
    (() => {
      const vis = el => { const r = el.getBoundingClientRect(); if (r.width<1||r.height<1) return false;
        const s = getComputedStyle(el); return s.visibility!=='hidden'&&s.display!=='none'&&s.opacity!=='0'; };
      for (const e of document.querySelectorAll('button,a,[role=button]')) {
        if (!vis(e)) continue;
        const txt = (e.innerText||'').trim();
        if (txt.includes(%s)) { const r=e.getBoundingClientRect();
          return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2,txt:txt.slice(0,60),disabled:!!e.disabled}); }
      }
      return null;
    })()
    """ % json.dumps(t, ensure_ascii=False)
    return send("Runtime.evaluate", expression=js, returnByValue=True).get("result", {}).get("value")


found = click_by_text(label)
print("TARGET:", found)
if not found:
    sys.exit("not found")
d = json.loads(found)
for ev in ("mousePressed", "mouseReleased"):
    send("Input.dispatchMouseEvent", type=ev, x=d["x"], y=d["y"], button="left", clickCount=1)

deadline = time.time() + settle / 1000
ws.settimeout(1.0)
events = []
while time.time() < deadline:
    try:
        msg = json.loads(ws.recv())
    except Exception:
        continue
    events.append(msg)

print("=== NETWORK (api only) ===")
seen = set()
for m in events:
    meth = m.get("method")
    p = m.get("params", {})
    if meth == "Network.requestWillBeSent":
        u = p.get("request", {}).get("url", "")
        if "/api/" in u:
            k = ("REQ", p["request"]["method"], u)
            if k in seen:
                continue
            seen.add(k)
            print("  REQ", p["request"]["method"], u[:150])
    elif meth == "Network.responseReceived":
        r = p.get("response", {})
        if "/api/" in r.get("url", "") or r.get("status", 0) >= 400:
            print("  RES", r.get("status"), r.get("url", "")[:150])
    elif meth == "Network.loadingFailed":
        print("  FAIL", p.get("errorText"), p.get("type"))

print("=== CONSOLE / EXCEPTIONS ===")
for m in events:
    meth = m.get("method")
    p = m.get("params", {})
    if meth == "Runtime.consoleAPICalled" and p.get("type") in ("error", "warning"):
        print("  ", p.get("type"), [a.get("value") or a.get("description", "") for a in p.get("args", [])])
    elif meth == "Runtime.exceptionThrown":
        ed = p.get("exceptionDetails", {})
        print("  EXC", (ed.get("exception") or {}).get("description", "")[:400])

post = send("Runtime.evaluate", expression="JSON.stringify({url:location.href, body:document.body.innerText.slice(0,200)})",
            returnByValue=True).get("result", {}).get("value")
print("POST:", post[:600])

r = send("Page.captureScreenshot", format="png")
(OUT / "watch-click.png").write_bytes(base64.b64decode(r["data"]))
print("shot:", OUT / "watch-click.png")
