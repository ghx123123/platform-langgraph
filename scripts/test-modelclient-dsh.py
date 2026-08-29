# test-modelclient-dsh.py — M6.2 验证: ModelClient(provider='dsh') 走完整 generate_json
import asyncio
import os
import sys
from pathlib import Path

PROJECT = Path(r"D:\paper\dsh\platform-langgraph")
sys.path.insert(0, str(PROJECT))
os.environ["MINIMAX_API_KEY"] = "sk-cp-Ce_tflcg9zHDE3dZkGs3UReFzTgM4k38Dqh3wlnXLEsYORBt0fd-RxU7xWcLDSksXkzUw9nzsyz_s6Oj32R_gDCDAzKHJDc9fKw1z0KAP-qrltx9BVa2m4w"

from backend.model_settings.models import RuntimeModelConfig
from backend.workflows.llm import ModelClient


async def main() -> None:
    client = ModelClient(RuntimeModelConfig(provider="dsh", model="minimax-m3", timeout_seconds=300))
    print("client:", client.provider, client.model_name)
    try:
        result = await client.generate_json(
            "你是知识大纲细化器, 只返回一个包含 nodes 的 JSON 对象, 不要解释。",
            '返回 {"nodes": [{"title": "Python 基础", "level": 1}, {"title": "变量", "level": 2}]}',
        )
        print("generate_json OK:", result)
        print("nodes:", len(result.get("nodes", [])))
    finally:
        # 显式关闭引擎, 确保清理子进程与管道
        engine = getattr(client, "_engine", None)
        if engine is not None:
            await engine.close()
            print("engine closed")


if __name__ == "__main__":
    asyncio.run(main())
