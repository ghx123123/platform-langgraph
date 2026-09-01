"""前端自动截图工具 — 支持多页面/多状态, 带元素定位
用 Playwright + 本机 Chrome 截图当前前端, 供分析 UI 布局/状态。

用法:
  python scripts/auto_screenshot.py                     # 默认首页
  python scripts/auto_screenshot.py --probe             # 输出当前可交互元素清单(tab/页面)
  python scripts/auto_screenshot.py --page=agent-flow   # 进生成过程视图
  python scripts/auto_screenshot.py --out=path.png
"""
import argparse, sys, time, json
from pathlib import Path

OUT = Path("C:/Users/84652/ui_shots"); OUT.mkdir(exist_ok=True)
CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe"
BASE = "http://127.0.0.1:5173"

def launch():
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    b = p.chromium.launch(executable_path=CHROME, headless=True, args=["--disable-gpu"])
    pg = b.new_page(viewport={"width": 1680, "height": 1050})
    return p, b, pg

def goto_home(pg):
    pg.goto(BASE, timeout=20000); pg.wait_for_timeout(2500)

def probe(pg):
    """输出页面上的 tab/按钮/关键文本, 便于知道点了什么"""
    print("=== 页面标题:", pg.title())
    tabs = pg.locator("button, .step, .workspace-tabs button").all_text_contents()[:40]
    print("=== 按钮/tab 文本:", [t.strip()[:24] for t in tabs if t.strip()])
    body = pg.inner_text("body")[:1200]
    print("=== body 前1200字:\n", body)

def step_into_design(pg):
    """进课程设计: 点顶部'第4步课程设计'或会话卡"""
    for kw in ["课程设计"]:
        try:
            pg.locator(f"text={kw}").first.click(timeout=3000)
            pg.wait_for_timeout(2000)
            break
        except Exception:
            pass

def step_into_flow(pg):
    """自动进到生成过程视图(AgentFlowWorkspace):
    1. 概览里点'课程设计'卡片 2. 选会话卡 3. 进'生成过程' tab
    """
    # 1. 概览卡片(带 inner_text 含'课程设计 生成、执行与打磨')
    for kw in ["生成、执行与打磨", "课程设计"]:
        try:
            pg.locator(f"div[class*=card], button, [class*=block]").filter(has_text=kw).first.click(timeout=4000)
            pg.wait_for_timeout(2200)
            print("  已点概览卡片:", kw)
            break
        except Exception as exc:
            print("  概览卡片失败", kw, str(exc)[:40])
    # 2. 选会话卡(优先带评分)
    for sel in [".session-card:has(.session-card-score)", ".session-card"]:
        try:
            pg.locator(sel).first.click(timeout=2500)
            print("  已点会话卡:", sel)
            break
        except Exception:
            continue
    pg.wait_for_timeout(3000)
    # 3. 进"生成过程" tab
    try:
        pg.locator("button:has-text('生成过程')").first.click(timeout=2000)
        pg.wait_for_timeout(1000)
    except Exception:
        pass

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="探测可交互元素")
    ap.add_argument("--page", default="home", choices=["home","process","flow"], help="目标页面")
    ap.add_argument("--out", default="", help="输出文件名")
    args = ap.parse_args()
    p, b, pg = launch()
    try:
        goto_home(pg)
        if args.probe:
            probe(pg)
        if args.page == "flow":
            step_into_flow(pg)
        name = args.out or f"ui_{args.page}_{time.strftime('%H%M%S')}.png"
        out = OUT / name
        pg.screenshot(path=str(out), full_page=False)
        print("截图已保存:", out)
    finally:
        b.close(); p.stop()

if __name__ == "__main__":
    main()
