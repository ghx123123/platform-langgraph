"""会话内浏览器驱动: 连接 9222 Chrome, 按选择器/文本点击, 截图。

用法示例:
  python scripts/drive.py click-card 1
  python scripts/drive.py click-text 生成过程
  python scripts/drive.py shot 名称
  python scripts/drive.py js "document.title"
"""
import json, time, sys, importlib.util, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("cdp", ROOT / "scripts" / "cdp.py")
cdp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdp)


class Driver:
    def __init__(self):
        self.c = cdp.Conn()
        self.c.send("Runtime.enable")
        self.c.send("Page.enable")
        self.c.eval(cdp.HELPERS_JS)

    def js(self, expr):
        return self.c.eval(expr)

    def shot(self, name):
        return self.c.shot(name)

    def _center(self, expr):
        raw = self.c.eval(
            "(function(){var el=%s; if(!el) return 'NOT_FOUND';"
            "el.scrollIntoView({block:'center'});"
            "var r=el.getBoundingClientRect();"
            "return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2,t:(el.innerText||el.value||'').replace(/\\n/g,' | ').slice(0,70)});})()" % expr
        )
        if raw == "NOT_FOUND" or not isinstance(raw, str):
            raise SystemExit("NOT_FOUND: %s -> %r" % (expr, raw))
        return json.loads(raw)

    def click(self, expr, wait=1.5, settle=0.5):
        d = self._center(expr)
        time.sleep(settle)
        d = self._center(expr)  # re-measure after scroll
        self.c.click_xy(d["x"], d["y"])
        time.sleep(wait)
        return d["t"]

    def click_text(self, text, tag="button,a,[role=button],.tab"):
        expr = "[...document.querySelectorAll('%s')].filter(e=>__cdp.visible(e)&&e.innerText&&e.innerText.trim().includes(%s))[0]" % (
            tag, json.dumps(text, ensure_ascii=False))
        return self.click(expr)


def main():
    d = Driver()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "shot"
    arg = sys.argv[2] if len(sys.argv) > 2 else ""
    if cmd == "shot":
        print(d.shot(arg or "drive-shot"))
    elif cmd == "js":
        print(json.dumps(d.js(arg), ensure_ascii=False, indent=1))
    elif cmd == "click-text":
        print("clicked:", d.click_text(arg))
    elif cmd == "click-card":
        print("clicked:", d.click("[...document.querySelectorAll('.session-card')][%s]" % arg, wait=5))
    elif cmd == "click-tab":
        print("clicked:", d.click("[...document.querySelectorAll('.workspace-tabs button')][%s]" % arg, wait=5))
    elif cmd == "click-sel":
        print("clicked:", d.click("document.querySelector(%s)" % json.dumps(arg), wait=4))
    elif cmd == "url":
        d.c.goto(arg); print("ok")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
