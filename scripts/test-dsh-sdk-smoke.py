# test-dsh-sdk-smoke.py — 从 platform-langgraph 复跑官方 Windows SDK 冒烟实验
# keyless: 本地 mock SSE 端点 + tsx 源码入口, 不依赖任何真实模型 key
import sys, os
from pathlib import Path

REPO_ROOT = Path(r'D:\paper\dsh\deepseek-harness')
sys.path.insert(0, str(Path(r'D:\paper\dsh\platform-langgraph\dev-venv-dshsdk\Lib\site-packages')))

smoke_path = REPO_ROOT / 'python' / 'sdk' / 'tests' / 'manual_sdk_agent_smoke.py'

import runpy
# 将标准输出留空, 便于我们看到打印内容
sys.argv = ['manual_sdk_agent_smoke.py', '--repo-root', str(REPO_ROOT)]
runpy.run_path(str(smoke_path), run_name='__main__')
