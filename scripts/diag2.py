import os
from pathlib import Path
os.environ["MINIMAX_API_KEY"] = "sk-cp-Ce_tflcg9zHDE3dZkGs3UReFzTgM4k38Dqh3wlnXLEsYORBt0fd-RxU7xWcLDSksXkzUw9nzsyz_s6Oj32R_gDCDAzKHJDc9fKw1z0KAP-qrltx9BVa2m4w"
from deepseek_harness import DeepSeekHarness
REPO = Path(r"D:\paper\dsh\deepseek-harness")
h = DeepSeekHarness(
    model="minimax-m3", cwd=r"D:\paper\dsh\platform-langgraph\.runtime\minimax-workspace",
    runtime_cwd=str(REPO), session_root=r"D:\paper\dsh\platform-langgraph\.runtime\minimax-session",
    cordis=r"D:\paper\dsh\platform-langgraph\.runtime\dsh-agent-cordis.yml",
    launch_args_override=("node", "--import", "tsx", str(REPO / "packages/examples/jsonrpc-demo/src/bin.ts")),
    env={"MINIMAX_API_KEY": os.environ["MINIMAX_API_KEY"], "DEEPSEEK_API_KEY": os.environ.get("DEEPSEEK_API_KEY", "")},
    request_timeout_seconds=60, shutdown_timeout_seconds=3,
)
h.start()
print("started")
r = h.run("1+1=?", session_id="direct-test-02")
print("finish_reason:", r.finish_reason)
print("events types:", [ev.get("type") for ev in r.events][:12])
for ev in r.events:
    t = ev.get("type")
    if t in ("agent/request-error", "turn/end", "step/end", "agent/error", "user/message", "llm/error"):
        print("EV", t, str(ev)[:280])
h.close()
