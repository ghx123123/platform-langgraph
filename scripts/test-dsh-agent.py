# test-dsh-agent.py — 最小实验: dsh Python SDK(JSON-RPC 智能体) 在 Windows 上能否跑通
# 用一个临时 workspace, 不碰任何现有数据
import os
import sys
import tempfile
from pathlib import Path

# 使用 venv 内已装好的 sdk (conda base 的 pydantic 被污染, 不能用)
# 运行时直接由 venv python 调用本脚本, 无需 sys.path hack

# 让 dsh agent 看到 miniconda 的环境, 保证子进程能正常初始化
AGENT_ENV = {}
for k in ('PATH', 'CONDA_PREFIX', 'CONDA_DEFAULT_ENV', 'CONDA_EXE', 'CONDA_PYTHON_EXE', 'DSH_HOME',
          'TEMP', 'TMP', 'USERPROFILE', 'APPDATA', 'ProgramFiles', 'ProgramW6432', 'ALLUSERSPROFILE', 'SYSTEMROOT'):
    if os.environ.get(k):
        AGENT_ENV[k] = os.environ[k]

workspace = Path(tempfile.mkdtemp(prefix='dsh-agent-test-'))
session_root = Path(tempfile.mkdtemp(prefix='dsh-agent-sessions-'))

print('== 实验配置 ==')
print('workspace:', workspace)
print('session_root:', session_root)
print('DSH_HOME:', os.environ.get('DSH_HOME'))
print('当前模型配置 (DSH_* / MODEL):', {k: v for k, v in os.environ.items() if k.startswith('DSH_') or 'MODEL' in k})

from deepseek_harness import DeepSeekHarness

# 明确指向本地构建完的 jsonrpc-demo bin (dsh-jsonrpc-agent), 因为 runtime-bin 无 win 包
NODE = r'C:\Program Files\nodejs\node.exe'
DEMO_BIN = r'D:\paper\dsh\deepseek-harness\packages\examples\jsonrpc-demo\lib\bin.js'

print('\n== 通过桥接 bin 调用智能体 (jsonrpc-demo + deepseek-official) ==')
try:
    with DeepSeekHarness(
        provider='deepseek-official',
        model=os.environ.get('DSH_MODEL', 'deepseek-v4-flash'),
        cwd=str(workspace),
        session_root=str(session_root),
        env=AGENT_ENV,
        bridge_bin=DEMO_BIN,
    ) as harness:
        result = harness.run('Say hi.')
        print('OK final_response:', (result.final_response or '')[:150])
        print('OK finish_reason:', result.finish_reason)
except Exception as e:
    print('FAIL:', type(e).__name__)
    print(str(e)[:500])

print('\n全流程结束')
