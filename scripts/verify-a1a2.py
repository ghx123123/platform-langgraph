"""验证 A1/A2: 桥长行扩容 + reader 崩溃后自愈。

1) 长输出不再触发 LimitOverrunError（A1）
2) 人为让 reader 崩溃后, 下一次请求能自动重建桥而不是白等 timeout（A2）
"""
import asyncio, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.workflows.dsh_engine import DshAgentEngine  # noqa: E402


async def main() -> None:
    engine = DshAgentEngine(default_model="minimax-m3")
    print("A1: 请求一段长输出 ...")
    t0 = time.time()
    chunks = 0
    final = ""
    async for item in engine.generate_stream(
        "你是课程教学设计助手。",
        "请用中文写一篇约 2500 字的 Python 第1章教学设计说明, 分成若干小节, 每节标题加粗。",
    ):
        if item.get("event") == "chunk":
            chunks += 1
            final += item.get("text") or ""
        elif item.get("event") == "done":
            final = item.get("final_response") or final
    print("A1: chunks=%d final_len=%d elapsed=%.1fs -> %s"
          % (chunks, len(final), time.time() - t0, "OK" if len(final) > 500 else "SUSPECT"))

    print("A2: 模拟 reader 崩溃(直接调用 _mark_unhealthy) ...")
    await engine._run_on_loop(engine._mark_unhealthy("simulated reader crash"), timeout=10)
    await asyncio.sleep(0.5)
    print("   healthy=%s reader_error=%s" % (engine._healthy, engine._reader_error))

    t1 = time.time()
    try:
        out = await engine.generate("你是助手。", "只回答两个字: 收到")
        print("A2: 自愈后请求成功 %.1fs -> %r" % (time.time() - t1, out[:40]))
    except Exception as exc:
        print("A2: *** 失败 %.1fs -> %s: %s" % (time.time() - t1, type(exc).__name__, exc))
    print("   healthy=%s restarts=%d" % (engine._healthy, len(engine._restarts)))


asyncio.run(main())
