# test-dsh-minimax-json.py — 验证 MiniMax-M3 经 dsh 智能体输出严格 JSON
# 这是替换 LangGraph 的关键前提: generate_json 需要严格 JSON 产出
import os
from pathlib import Path as P

os.environ['MINIMAX_API_KEY'] = 'sk-cp-Ce_tflcg9zHDE3dZkGs3UReFzTgM4k38Dqh3wlnXLEsYORBt0fd-RxU7xWcLDSksXkzUw9nzsyz_s6Oj32R_gDCDAzKHJDc9fKw1z0KAP-qrltx9BVa2m4w'

from deepseek_harness import DeepSeekHarness

REPO_ROOT = r'D:\paper\dsh\deepseek-harness'
CORDIS = r'D:\paper\dsh\platform-langgraph\.runtime\minimax-cordis.yml'

PROMPT = (
    "严格按以下格式输出 JSON，不要输出任何多余内容（不要 markdown 代码块、不要解释、不要 think 标签）:\n"
    '{"nodes":[{"title":"概念","level":1}]}'  # 提示: 生成一个包含 5 个知识点的小大纲
    "\n\n任务: 将 Python 入门课程的第 1 列知识点整理为 JSON 大纲，最多 5 个节点。"
)

print('== JSON 结构化输出实验 (MiniMax-M3 + dsh 智能体) ==')
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
    result = harness.run(PROMPT, session_id='minimax-m3-json-01')
    final = result.final_response or ''
    print('final_response:', final[:500])
    print('finish_reason:', result.finish_reason)
    # 尝试提取 JSON
    import re, json
    m = re.search(r'\{[\s\S]*\}', final)
    if m:
        raw = m.group(0).replace('```json', '').replace('```', '')
        try:
            parsed = json.loads(raw)
            print('JSON_PARSE_OK, nodes:', len(parsed.get('nodes', [])))
        except Exception as e:
            print('JSON_PARSE_FAIL:', str(e)[:150])
            print('raw:', raw[:300])
    else:
        print('NO_JSON_FOUND')
print('== 完成 ==')
