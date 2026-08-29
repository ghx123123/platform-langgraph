# test-dsh-engine.py — M6.1b 引擎单测: DshAgentEngine 直接调 MiniMax-M3 返回 JSON
import asyncio
import os
import sys
from pathlib import Path

PROJECT = Path(r"D:\paper\dsh\platform-langgraph")
sys.path.insert(0, str(PROJECT))

# 完整 MiniMax key 注入(与平台相同; 若平台已注入, 该行覆盖)
os.environ["MINIMAX_API_KEY"] = "sk-cp-Ce_tflcg9zHDE3dZkGs3UReFzTgM4k38Dqh3wlnXLEsYORBt0fd-RxU7xWcLDSksXkzUw9nzsyz_s6Oj32R_gDCDAzKHJDc9fKw1z0KAP-qrltx9BVa2m4w"

from backend.workflows.dsh_engine import DshAgentEngine


async def main() -> None:
    engine = DshAgentEngine(default_model="minimax-m3")
    await engine.ensure_started()
    print("engine started")
    try:
        text = await engine.generate(
            "你是知识大纲细化器, 只输出一个 JSON 对象, 不要解释。",
            '返回 {"nodes": [{"title": "大纲标题", "level": 1}]}',
        )
        print("generate ok:", text[:300])
    finally:
        await engine.close()
        print("engine closed")


if __name__ == "__main__":
    asyncio.run(main())
