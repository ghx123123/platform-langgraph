"""隔离验证: dsh 桥 stdout 单行长度是否触发 asyncio StreamReader LimitOverrunError。

直接用与 backend/workflows/dsh_engine.py 相同的方式 spawn 桥, 发一个流式 generate,
记录每行字节数, 找出最大行与是否崩溃。
"""
import asyncio, json, os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRIDGE = ROOT / "scripts" / "dsh_agent_bridge.py"
VENV_PY = ROOT / "dev-venv-dshsdk" / "Scripts" / "python.exe"
MODEL = "minimax-m3"


async def main():
    env = dict(os.environ)
    env.update({
        "DSH_CWD": str(ROOT), "DSH_SESSION_ROOT": str(ROOT / ".dsh-sessions"),
        "DSH_MODEL": MODEL, "PYTHONUTF8": "1",
    })
    proc = await asyncio.create_subprocess_exec(
        str(VENV_PY), "-X", "utf8", str(BRIDGE),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, cwd=str(ROOT), env=env,
    )

    async def probe():
        proc.stdin.write((json.dumps({"id": 0, "method": "probe"}) + "\n").encode())
        await proc.stdin.drain()
        line = await proc.stdout.readline()
        print("probe:", line.decode("utf-8", errors="replace")[:200])

    await probe()

    # 流式 generate: 让模型输出一段长文本, 观察单行长度
    req = {
        "id": 1, "method": "generate",
        "params": {
            "stream": True, "model": MODEL,
            "session_id": "probe-pipe-limit",
            "system_prompt": "你是课程教学设计助手。",
            "user_prompt": "请用中文写一篇 3000 字左右的 Python 第1章教学设计说明, 分成若干小节, 每节标题加粗。",
        },
    }
    proc.stdin.write((json.dumps(req, ensure_ascii=False) + "\n").encode())
    await proc.stdin.drain()

    sizes = []
    t0 = time.time()
    chunks = 0
    try:
        while True:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=240)
            if not line:
                print("EOF"); break
            sizes.append(len(line))
            try:
                msg = json.loads(line)
            except Exception:
                print("non-JSON line of %d bytes" % len(line)); continue
            if msg.get("event") in ("chunk", "phase", "request"):
                if msg.get("event") == "chunk":
                    chunks += 1
                if chunks % 200 == 0 and msg.get("event") == "chunk":
                    print("... %d chunks, max line so far %d" % (chunks, max(sizes)))
                continue
            print("final msg keys:", list(msg.keys()), "| ok=", msg.get("ok"),
                  "| final_len=", len(msg.get("final_response") or ""),
                  "| reason=", msg.get("finish_reason"), "| err=", str(msg.get("error"))[:200])
            break
    except asyncio.LimitOverrunError as e:
        print("*** LimitOverrunError reproduced:", e)
    except asyncio.TimeoutError:
        print("*** readline timeout")
    except Exception as e:
        print("*** %s: %s" % (type(e).__name__, e))
    finally:
        sizes.sort()
        print("lines=%d max=%d p99=%d median=%d elapsed=%.1fs"
              % (len(sizes), sizes[-1] if sizes else 0,
                 sizes[int(len(sizes)*0.99)] if sizes else 0,
                 sizes[len(sizes)//2] if sizes else 0, time.time()-t0))
        proc.kill()


asyncio.run(main())
