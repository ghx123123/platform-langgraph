# dsh_agent_bridge.py — 平台内嵌 dsh 智能体 stdio 桥
# 由 platform 后端进程 spawn(venv python 运行), 通过 stdio JSON-RPC 调用 SDK
#
# 协议: 每行一个 JSON
#   请求: {"id": <int>, "method": "generate", "params": {"system_prompt": str, "user_prompt": str, "session_id": str, "model": str}}
#   响应: {"id": <int>, "ok": true, "final_response": str, "finish_reason": str}
#        {"id": <int>, "ok": false, "error": str}
#   probe: {"id": 0, "method": "probe"} -> {"id": 0, "ok": true, "version": "..."}
#   agent_run: 同一 session 内多轮自主迭代(记忆+自查收敛)
#     请求: {"method":"agent_run","params":{"system_prompt","user_prompt","session_id","model","iterations","round_focus"}}
#     响应: {"ok":true,"final_response":str,"finish_reason":str,"iterations":int}
#
# v0.3.2 — agent_run: 复用 session 的多轮自主迭代(每轮基于上一轮产出修订, 越迭代越收敛)

import json
import logging
import os
import sys
from pathlib import Path

from deepseek_harness import DeepSeekHarness

BRIDGE_VERSION = "0.3.2"

# pi-ai catalog 动态补丁: deepseek.json 未收录官网新模型(如 deepseek-v4-flash-vision-exp)
# 时自动补入(以 flash 为模板 + vision 输入), 幂等。避免"has no configured model"。
def ensure_deepseek_vision_catalog() -> bool:
    import glob
    import json as _json

    # 桥由 platform 项目 cwd 启动; pi-ai 目录在 harness 仓库的 node_modules(.pnpm)里
    candidates = [
        str(REPO_ROOT / "node_modules" / ".pnpm" / "@earendil-works+pi-ai*" / "node_modules" / "@earendil-works" / "pi-ai" / "dist" / "providers" / "data" / "deepseek.json"),
        "node_modules/.pnpm/@earendil-works+pi-ai*/node_modules/@earendil-works/pi-ai/dist/providers/data/deepseek.json",
        r"D:/paper/dsh/**/pi-ai/dist/providers/data/deepseek.json",
    ]
    try:
        files = []
        for cand in candidates:
            files = glob.glob(cand)
            if files:
                break
        if not files:
            return False
        path = files[0]
        with open(path, encoding="utf-8") as f:
            data = _json.load(f)
        oc = data.get("openai-completions") or {}
        missing = []
        for mid in ("deepseek-v4-flash-vision-exp",):
            if mid not in oc:
                flash = oc.get("deepseek-v4-flash")
                if not flash:
                    continue
                vision = dict(flash)
                vision.update({
                    "id": mid,
                    "name": "DeepSeek V4 Flash Vision",
                    "input": ["text", "image"],
                    # vision-exp 虽返回 reasoning_content, 但按 chat 模型走:
                    # 去除推理严格兼容(requiresReasoningContentOnAssistantMessages/thinkingFormat),
                    # 否则 pi-ai 按推理格式请求/解析会卡死(实测 300s 无响应)。
                    "compat": dict(flash.get("compat") or {}, **{
                        "requiresReasoningContentOnAssistantMessages": False,
                        "thinkingFormat": None,
                    }),
                })
                oc[mid] = vision
                missing.append(mid)
        if missing:
            with open(path, "w", encoding="utf-8") as f:
                _json.dump(data, f, ensure_ascii=False, indent=1)
            return True
        return False
    except Exception:
        return False

# 平台配置的 model name -> (pi-ai catalog provider, 模型 id)
# 注意: 必须与 pi-ai @earendil-works 0.82 的 catalog 保持一致——
# deepseek: deepseek-v4-flash / deepseek-v4-pro 已收录, vision-exp 未收录(选了会报
# "provider has no configured model"), 因此不在此列, 面板探测也把它过滤掉。
MODEL_ROUTES = {
    "minimax-m3": ("minimax-cn", "MiniMax-M3"),
    "minimax-m2.7": ("minimax-cn", "MiniMax-M2.7"),
    "deepseek-v4-flash": ("deepseek", "deepseek-v4-flash"),
    "deepseek-v4-pro": ("deepseek", "deepseek-v4-pro"),
    "deepseek-v4-flash-vision-exp": ("deepseek", "deepseek-v4-flash-vision-exp"),
}

REPO_ROOT = Path(r"D:\paper\dsh\deepseek-harness")
CORDIS = Path(
    os.environ.get(
        "DSH_CORDIS",
        str(Path(__file__).resolve().parent.parent / ".runtime" / "dsh-agent-cordis.yml"),
    )
)

_bridge_lock = __import__("threading").Lock()
STATE = {"harness": None, "provider": None, "model": None}


def translate_error(text: str) -> str:
    """把 dsh/SDK 常见的模型错误翻译成中文提示."""
    low = text.lower()
    if "429" in text or "rate_limit" in low or "token plan" in low:
        return f"模型额度不足（429 限流）：{text[:160]}。请切换模型或为当前模型充值。"
    if "401" in text or "unauthorized" in low or "invalid_api_key" in low or "invalid api key" in low:
        return f"API Key 无效（401）：{text[:160]}。请检查环境变量中的 API KEY。"
    if "400" in text and ("invalid" in low or "bad request" in low):
        return f"请求参数错误（400）：{text[:160]}。"
    if "500" in text or "internal" in low:
        return f"模型服务错误（500）：{text[:160]}。"
    if "timeout" in low or "timed out" in low:
        return f"模型响应超时：{text[:160]}。"
    if "context" in low and "too long" in low or "exceeds" in low and "window" in low:
        return f"上下文过长：{text[:160]}。请缩短提问文本。"
    return text


def ensure_harness(workdir: Path, session_root: Path, model: str) -> DeepSeekHarness:
    """保证当前 harness 的 provider/model 匹配请求。不匹配则销毁重建(换模型)。"""
    provider, model_id = MODEL_ROUTES.get(model, MODEL_ROUTES[os.environ.get("DSH_MODEL", "minimax-m3")])
    with _bridge_lock:
        state = STATE
        if state["harness"] is not None and state["provider"] == provider and state["model"] == model_id:
            return state["harness"]
        old = state["harness"]
        if old is not None:
            try:
                old.close()
            except Exception:
                pass
            state["harness"] = None
        api_key_env = (os.environ.get("MINIMAX_API_KEY") if provider == "minimax-cn" else os.environ.get("DEEPSEEK_API_KEY")) or ""
        log = logging.getLogger("dsh_bridge")
        log.info("rebuild harness provider=%s model=%s has_key=%s", provider, model_id, bool(api_key_env))
        harness = DeepSeekHarness(
            provider=provider,
            model=model_id,
            cwd=str(workdir),
            runtime_cwd=str(REPO_ROOT),
            session_root=str(session_root),
            cordis=str(CORDIS),
            launch_args_override=(
                "node", "--import", "tsx",
                str(REPO_ROOT / "packages/examples/jsonrpc-demo/src/bin.ts"),
            ),
            env={
                "MINIMAX_API_KEY": os.environ.get("MINIMAX_API_KEY", ""),
                "DEEPSEEK_API_KEY": os.environ.get("DEEPSEEK_API_KEY", ""),
                "DSH_MODEL": model,
            },
            request_timeout_seconds=240,
            shutdown_timeout_seconds=10,
        )
        harness.start()
        state["harness"] = harness
        state["provider"] = provider
        state["model"] = model_id
        return harness


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr)
    log = logging.getLogger("dsh_bridge")

    api_key_env = os.environ.get("MINIMAX_API_KEY", "")
    workdir = Path(os.environ.get("DSH_CWD", str(Path.cwd())))
    workdir.mkdir(parents=True, exist_ok=True)
    session_root = Path(os.environ.get("DSH_SESSION_ROOT", str(workdir / ".dsh-sessions")))
    session_root.mkdir(parents=True, exist_ok=True)
    default_model = str(os.environ.get("DSH_MODEL", "minimax-m3"))

    log.info("bridge start cordis=%s model=%s has_minimax_key=%s has_deepseek_key=%s workdir=%s",
             CORDIS, default_model, bool(api_key_env), bool(os.environ.get("DEEPSEEK_API_KEY")), workdir)

    # pi-ai 目录补丁: 官网模型未收录时注入(生效一次, 后续幂等)
    if ensure_deepseek_vision_catalog():
        log.info("pi-ai deepseek catalog patched (vision model added)")

    # 初次启动按默认模型建 harness(失败也不阻塞: 请求时按需重建)
    try:
        ensure_harness(workdir, session_root, default_model)
        state = STATE
        log.info("harness started provider=%s model=%s", state["provider"], state["model"])
    except Exception as exc:
        log.error("initial harness start failed: %s", exc)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            print(json.dumps({"id": -1, "ok": False, "error": f"bad request: {exc}"}, ensure_ascii=False), flush=True)
            continue

        rid = req.get("id", -1)
        method = req.get("method")
        try:
            if method == "probe":
                print(json.dumps({"id": rid, "ok": True, "version": BRIDGE_VERSION, "model": default_model}, ensure_ascii=False), flush=True)
                continue

            if method == "generate":
                params = req.get("params", {})
                system_prompt = str(params.get("system_prompt", ""))
                user_prompt = str(params.get("user_prompt", ""))
                session_id = str(params.get("session_id", ""))
                model = str(params.get("model", default_model))
                provider, model_id = MODEL_ROUTES.get(model, MODEL_ROUTES[default_model])

                task_prompt = (
                    f"请严格按以下指令完成任务, 不要做多余解释。\n\n"
                    f"【你的职责】\n{system_prompt}\n\n"
                    f"【任务内容】\n{user_prompt}"
                )

                log.info("generate id=%s model=%s (%s/%s) session=%s", rid, model, provider, model_id, session_id or "new")
                harness = ensure_harness(workdir, session_root, model)
                result = harness.run(task_prompt, session_id=session_id or None)
                final = result.final_response or ""
                reason = result.finish_reason or ""
                if reason == "error":
                    # SDK 的 429/限流等错误可能在 events 的 turn/end reason.error.message 里,
                    # 未必出现在 final_response —— 从事件里提取真实原因再翻译。
                    err_text = ""
                    for ev in reversed(getattr(result, "events", []) or []):
                        data = ev.get("data") if isinstance(ev, dict) else None
                        if isinstance(data, dict) and ev.get("type") == "turn/end":
                            reason_obj = data.get("reason") or {}
                            err_text = (reason_obj.get("error") or {}).get("message") or (reason_obj.get("failure") or {}).get("message") or ""
                            if err_text:
                                break
                    err_text = translate_error(err_text or final or "模型调用失败，请稍后重试")
                    print(json.dumps({
                        "id": rid, "ok": True,
                        "final_response": final,
                        "finish_reason": "error",
                        "error": err_text,
                    }, ensure_ascii=False), flush=True)
                    continue
                print(json.dumps({
                    "id": rid, "ok": True,
                    "final_response": final,
                    "finish_reason": reason,
                }, ensure_ascii=False), flush=True)
                continue

            if method == "agent_run":
                # 自主迭代: 同一 session 内做 N 轮, 每轮基于上一轮产出自查修订, 越迭代越收敛。
                # 多轮记忆: 复用 session_id(不换新), dsh 记住此前各轮内容。
                params = req.get("params", {})
                system_prompt = str(params.get("system_prompt", ""))
                user_prompt = str(params.get("user_prompt", ""))
                session_id = str(params.get("session_id", ""))
                model = str(params.get("model", default_model))
                iterations = max(1, min(int(params.get("iterations", 2)), 5))
                round_focus = str(params.get("round_focus", "请把上一版成果规范化、补全遗漏、修正疏漏，并给出更完整、更可用的最终版。"))
                provider, model_id = MODEL_ROUTES.get(model, MODEL_ROUTES[default_model])

                iterations_done = 0
                last_final = ""
                reasons = []
                harness = ensure_harness(workdir, session_root, model)
                for i in range(1, iterations + 1):
                    if i == 1:
                        task_prompt = (
                            f"请严格按以下指令完成任务, 不要做多余解释。\n\n"
                            f"【你的职责】\n{system_prompt}\n\n"
                            f"【任务内容】\n{user_prompt}"
                        )
                    else:
                        task_prompt = (
                            f"请严格按以下指令完成任务。这是第 {i}/{iterations} 轮迭代。\n\n"
                            f"【你的职责】\n{system_prompt}\n\n"
                            f"【上一版成果】\n{last_final}\n\n"
                            f"【本轮修订要求】\n{round_focus}\n\n"
                            f"【原始任务】\n{user_prompt}"
                        )
                    log.info("agent_run round=%s/%s id=%s model=%s session=%s", i, iterations, rid, model, session_id or "new")
                    result = harness.run(task_prompt, session_id=session_id or None)
                    last_final = result.final_response or ""
                    reason = result.finish_reason or ""
                    iterations_done = i
                    if reason == "error":
                        err_text = ""
                        for ev in reversed(getattr(result, "events", []) or []):
                            data = ev.get("data") if isinstance(ev, dict) else None
                            if isinstance(data, dict) and ev.get("type") == "turn/end":
                                reason_obj = data.get("reason") or {}
                                err_text = (reason_obj.get("error") or {}).get("message") or (reason_obj.get("failure") or {}).get("message") or ""
                                if err_text:
                                    break
                        err_text = translate_error(err_text or last_final or "模型调用失败，请稍后重试")
                        print(json.dumps({
                            "id": rid, "ok": True,
                            "final_response": last_final,
                            "finish_reason": "error",
                            "iterations": iterations_done,
                            "error": err_text,
                        }, ensure_ascii=False), flush=True)
                        break
                    reasons.append(reason)

                print(json.dumps({
                    "id": rid, "ok": True,
                    "final_response": last_final,
                    "finish_reason": reasons[-1] if reasons else "",
                    "iterations": iterations_done,
                    "turns": [{"round": i + 1, "finish_reason": reasons[i]} for i in range(len(reasons))],
                }, ensure_ascii=False), flush=True)
                continue

            print(json.dumps({"id": rid, "ok": False, "error": f"unknown method {method}"}, ensure_ascii=False), flush=True)
        except Exception as exc:
            log.error("request failed: %s", exc)
            print(json.dumps({"id": rid, "ok": False, "error": translate_error(str(exc)[:500])}, ensure_ascii=False), flush=True)

    state = STATE
    if state["harness"] is not None:
        state["harness"].close()
    log.info("bridge stop")


if __name__ == "__main__":
    main()
