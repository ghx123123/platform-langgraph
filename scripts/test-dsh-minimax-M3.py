# test-dsh-minimax-M3.py — 路径乙: 用 pi-ai 的 minimax-cn provider 驱动 dsh 智能体
# minimax-cn 是内置 catalog 路由(api.minimaxi.com/anthropic, 有 MiniMax-M3 条目, 无 [DONE] SSE 坑)
import os
from pathlib import Path

# 完整 MiniMax key (必须覆盖, 环境变量里是截断的)
os.environ['MINIMAX_API_KEY'] = 'sk-cp-Ce_tflcg9zHDE3dZkGs3UReFzTgM4k38Dqh3wlnXLEsYORBt0fd-RxU7xWcLDSksXkzUw9nzsyz_s6Oj32R_gDCDAzKHJDc9fKw1z0KAP-qrltx9BVa2m4w'

from deepseek_harness import DeepSeekHarness
from pathlib import Path as P

REPO_ROOT = r'D:\paper\dsh\deepseek-harness'
CORDIS = r'D:\paper\dsh\platform-langgraph\.runtime\minimax-cordis.yml'

print('== 路径乙: pi-ai minimax-cn + MiniMax-M3 驱动 dsh 智能体 ==')
with DeepSeekHarness(
    provider='minimax-cn',
    model='MiniMax-M3',
    cwd=r'D:\paper\dsh\platform-langgraph\.runtime\minimax-workspace',
    runtime_cwd=REPO_ROOT,
    session_root=r'D:\paper\dsh\platform-langgraph\.runtime\minimax-session',
    cordis=CORDIS,
    launch_args_override=('node', '--import', 'tsx', str(P(REPO_ROOT) / 'packages/examples/jsonrpc-demo/src/bin.ts')),
    env={
        'MINIMAX_API_KEY': os.environ['MINIMAX_API_KEY'],
        'DSH_MODEL': 'MiniMax-M3',
    },
    request_timeout_seconds=180,
    shutdown_timeout_seconds=5,
) as harness:
    result = harness.run('用一句中文回答: 你好,你是谁?', session_id='minimax-m3-piai-01')
    print('final_response:', (result.final_response or '')[:300])
    print('finish_reason:', result.finish_reason)
print('== 完成 ==')
