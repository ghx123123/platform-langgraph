import json
import re
from contextvars import ContextVar, Token
from math import ceil
from time import perf_counter
from typing import Any, Awaitable, Callable

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from backend.workflows.dsh_engine import DshAgentEngine

class ModelClient:
    def __init__(self, settings: Any) -> None:
        runtime = hasattr(settings, "provider")
        self.provider = settings.provider if runtime else settings.llm_provider
        model_name = settings.model if runtime else settings.llm_model
        api_key = settings.api_key if runtime else settings.llm_api_key
        base_url = settings.base_url if runtime else settings.llm_base_url
        temperature = settings.temperature if runtime else settings.llm_temperature
        timeout = settings.timeout_seconds if runtime else settings.llm_timeout_seconds
        self.model_name = model_name if self.provider != "mock" else "deterministic-mock"
        self._metrics_trace: ContextVar[list[dict[str, Any]] | None] = ContextVar(
            f"model_metrics_{id(self)}", default=None
        )
        self._model = None
        if self.provider == "openai_compatible":
            self._model = ChatOpenAI(
                model=model_name,
                api_key=api_key,
                base_url=base_url,
                temperature=temperature,
                timeout=timeout,
                max_retries=2,
            )
        elif self.provider == "dsh":
            # dsh 智能体: 内嵌 SDK 子进程(stdio 桥), 每次调用新 session
            # 面板填的 API Key 直接由桥使用(override 进程 env), 这样切换 dsh 厂商无需重启进程
            self._engine: DshAgentEngine | None = None
            self._dsh_api_key: str = api_key or ""
            self._dsh_base_url: str = base_url or ""

    @property
    def is_mock(self) -> bool:
        return self.provider == "mock"

    def ensure_dsh_engine(self) -> DshAgentEngine:
        """dsh 引擎(懒创建/模型变化时重建)。模型名跟随当前设置, 供 generate 与 graph_router 共用;
        调用方负责在模型变化时处理旧引擎生命周期。"""
        want = self.model_name or "deepseek-v4-flash"
        if self._engine is None or getattr(self._engine, "default_model", "") != want:
            self._engine = DshAgentEngine(default_model=want, api_key=self._dsh_api_key or None, base_url=self._dsh_base_url or None)
        return self._engine

    def begin_metrics_trace(self) -> Token:
        return self._metrics_trace.set([])

    def end_metrics_trace(self, token: Token) -> None:
        self._metrics_trace.reset(token)

    def metrics_count(self) -> int:
        return len(self._metrics_trace.get() or [])

    def metrics_since(self, index: int) -> dict[str, Any]:
        entries = (self._metrics_trace.get() or [])[index:]
        response_ms = sum(int(item["response_ms"]) for item in entries)
        output_tokens = sum(int(item["output_tokens"]) for item in entries)
        return {
            "request_count": len(entries),
            "response_ms": response_ms,
            "max_response_ms": max((int(item["response_ms"]) for item in entries), default=0),
            "input_tokens": sum(int(item["input_tokens"]) for item in entries),
            "output_tokens": output_tokens,
            "total_tokens": sum(int(item["total_tokens"]) for item in entries),
            "estimated": any(bool(item["estimated"]) for item in entries),
            "output_tokens_per_second": round(output_tokens / (response_ms / 1000), 1) if response_ms else 0,
        }

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
        remainder = len(re.sub(r"[\u4e00-\u9fff\s]", "", text))
        return chinese + ceil(remainder / 4)

    @staticmethod
    def _response_usage(response: Any) -> tuple[int, int, int] | None:
        usage = getattr(response, "usage_metadata", None) or {}
        if usage:
            input_tokens = int(usage.get("input_tokens") or 0)
            output_tokens = int(usage.get("output_tokens") or 0)
            total_tokens = int(usage.get("total_tokens") or input_tokens + output_tokens)
            if total_tokens:
                return input_tokens, output_tokens, total_tokens
        token_usage = (getattr(response, "response_metadata", None) or {}).get("token_usage", {})
        if token_usage:
            input_tokens = int(token_usage.get("prompt_tokens") or token_usage.get("input_tokens") or 0)
            output_tokens = int(token_usage.get("completion_tokens") or token_usage.get("output_tokens") or 0)
            total_tokens = int(token_usage.get("total_tokens") or input_tokens + output_tokens)
            if total_tokens:
                return input_tokens, output_tokens, total_tokens
        return None

    def _record_metrics(
        self,
        started: float,
        system_prompt: str,
        user_prompt: str,
        output: str,
        response: Any = None,
    ) -> None:
        trace = self._metrics_trace.get()
        if trace is None:
            return
        actual = self._response_usage(response) if response is not None else None
        if actual:
            input_tokens, output_tokens, total_tokens = actual
            estimated = False
        else:
            input_tokens = self._estimate_tokens(system_prompt + "\n" + user_prompt)
            output_tokens = self._estimate_tokens(output)
            total_tokens = input_tokens + output_tokens
            estimated = True
        trace.append({
            "response_ms": max(1, round((perf_counter() - started) * 1000)),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "estimated": estimated,
        })

    async def generate(self, system_prompt: str, user_prompt: str, on_chunk: Callable[[str], Awaitable[None]] | None = None) -> str:
        started = perf_counter()
        if self.provider == "dsh":
            # dsh 智能体: 内嵌引擎复用子进程; 模型变了(设置面板切换) → 重建引擎(桥按新模型重建 harness)
            if self._engine is not None and getattr(self._engine, "default_model", None) != self.model_name:
                await self._engine.close()
                self._engine = None
            engine = self.ensure_dsh_engine()
            if on_chunk is not None:
                # 流式: engine.generate_stream 逐 chunk 回调 on_chunk(供 emit node.token), 拼 final 返回
                parts: list[str] = []
                async for item in engine.generate_stream(system_prompt, user_prompt, model=self.model_name):
                    if item.get("event") == "chunk":
                        text = str(item.get("text") or "")
                        parts.append(text)
                        await on_chunk(text)
                    elif item.get("event") == "done":
                        parts = [str(item.get("final_response") or "")]
                output = "".join(parts) or (await engine.generate(system_prompt, user_prompt, model=self.model_name))
            else:
                output = await engine.generate(system_prompt, user_prompt, model=self.model_name)
            self._record_metrics(started, system_prompt, user_prompt, output)
            return output
        if self._model is None:
            output = self._mock_response(system_prompt, user_prompt)
            self._record_metrics(started, system_prompt, user_prompt, output)
            return output
        response = await self._model.ainvoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        )
        output = self._strip_reasoning(str(response.content))
        self._record_metrics(started, system_prompt, user_prompt, output, response)
        return output

    async def agent_iterate(
        self,
        system_prompt: str,
        user_prompt: str,
        iterations: int = 2,
        session_id: str | None = None,
        round_focus: str | None = None,
    ) -> dict:
        """dsh 多轮自主迭代(复用 session 保记忆)。非 dsh provider 时退化为单次 generate。

        return {"final_response", "iterations", "turns"}。
        用于内容分析/教学设计等需要连贯、可自查收敛的关键节点:
        dsh 在同一 session 内多轮修订并记住上下文, 而非每轮失忆的单次调用。
        """
        if self.provider != "dsh":
            output = await self.generate(system_prompt, user_prompt)
            return {"final_response": output, "iterations": 1, "turns": []}
        if self._engine is not None and getattr(self._engine, "default_model", None) != self.model_name:
            await self._engine.close()
            self._engine = None
        engine = self.ensure_dsh_engine()
        started = perf_counter()
        result = await engine.agent_run(
            system_prompt, user_prompt, iterations=iterations,
            model=self.model_name, session_id=session_id, round_focus=round_focus,
        )
        self._record_metrics(started, system_prompt, user_prompt, result.get("final_response", ""))
        return result

    async def generate_stream(self, system_prompt: str, user_prompt: str):
        """dsh 流式生成: async generator, 逐 chunk yield {"event":"chunk","text"} 等真实事件。

        供 workflow emit 成 node.token 流事件, 让前端看到"真实正在生成的过程"。
        非 dsh provider 退化为单次 generate(仅 yield done)。
        """
        if self.provider != "dsh":
            output = await self.generate(system_prompt, user_prompt)
            yield {"event": "done", "final_response": output}
            return
        if self._engine is not None and getattr(self._engine, "default_model", None) != self.model_name:
            await self._engine.close()
            self._engine = None
        engine = self.ensure_dsh_engine()
        async for item in engine.generate_stream(system_prompt, user_prompt, model=self.model_name):
            yield item

    @staticmethod
    def _strip_reasoning(text: str) -> str:
        """移除推理模型的思维链，避免 <think> 内容出现在课堂记录里。"""
        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
        # 思维链未闭合时（截断输出），保留结束标签之后的正文
        if re.search(r"<think>", cleaned, re.IGNORECASE):
            cleaned = re.split(r"</think>", cleaned, maxsplit=1, flags=re.IGNORECASE)[-1]
            cleaned = re.sub(r"^[\s\S]*<think>", "", cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    async def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        text = await self.generate(system_prompt, user_prompt)
        return self._extract_json_text(text)

    @classmethod
    def _extract_json_text(cls, text: str) -> dict[str, Any]:
        """从任意模型输出中稳健提取 JSON 对象(剥代码块 + 取最大括号配平对象)。纯函数, 不产生第二次调用。"""
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            # 取最外层完整对象：括号配平，避免截断到说明性文字里的片段
            match = cls._balanced_object(cleaned)
            if match is None:
                raise ValueError("Model response did not contain a JSON object")
            parsed = json.loads(match)
        if not isinstance(parsed, dict):
            raise ValueError("Model response JSON must be an object")
        return parsed

    @staticmethod
    def _balanced_object(text: str) -> str | None:
        candidates: list[str] = []
        start = text.find("{")
        while start != -1:
            depth = 0
            in_string = False
            escaped = False
            for index in range(start, len(text)):
                char = text[index]
                if in_string:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == '"':
                        in_string = False
                    continue
                if char == '"':
                    in_string = True
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start : index + 1]
                        try:
                            json.loads(candidate)
                        except json.JSONDecodeError:
                            # 括号配平但 json.loads 失败(可能含未加引号的注释/尾部文字)的候选
                            # 记入失败候选但不丢弃, 跳到下一个 '{' 再试, 取所有能配平的候选里最大。
                            break
                        candidates.append(candidate)
                        break
            start = text.find("{", start + 1)
        # Models sometimes put a small example object before the requested
        # payload. The top-level answer is normally the largest valid object.
        return max(candidates, key=len) if candidates else None

    _STOPWORDS = frozenset({"课程", "材料", "内容", "学习", "教学", "重点", "难点", "知识点", "核心", "本章", "小结", "习题"})
    _PROMPT_LABELS = "课程|材料依据|材料|补充说明|内容分析|总轮次|教学框架|上轮督导|本轮重点|对照知识点|教师刚才讲授|学生问题|本轮课堂记录|候选知识点"

    @staticmethod
    def _prompt_line(user_prompt: str, label: str) -> str:
        match = re.search(rf"^{label}[：:]\s*(.*)$", user_prompt, re.MULTILINE)
        return match.group(1).strip() if match else ""

    @classmethod
    def _prompt_block(cls, user_prompt: str, label: str) -> str:
        pattern = rf"^{label}[：:]\s*(.*?)(?=^(?:{cls._PROMPT_LABELS})[：:]|\Z)"
        match = re.search(pattern, user_prompt, re.MULTILINE | re.DOTALL)
        return match.group(1).strip() if match else ""

    @classmethod
    def _salient_terms(cls, text: str, limit: int = 6, exclude: str = "") -> list[str]:
        """从课程材料中抽取代表性术语，使演示模型的产出与上传文档相关。

        标题行优先；整句（含谓语的长句）降级为补充来源，避免把叙述句当成知识点。
        """
        headings: list[str] = []
        body: list[str] = []
        for line in re.sub(r"[{}\[\]'\"《》【】]", " ", text).splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if ">>" in stripped:  # Python 交互式解释器代码行
                continue
            if stripped.startswith("#") and re.search(r"[()=]", stripped):
                continue  # Python 代码注释，不是 Markdown 标题
            cleaned = re.sub(r"^[#\s\-•*\d.、()（）]+", "", stripped).strip(" ：:")
            cleaned = re.sub(r"^第.{1,8}[章节]\s*", "", cleaned).strip()
            if cleaned:
                (headings if stripped.startswith("#") else body).append(cleaned)

        excluded = {item for item in (exclude.strip(),) if item}
        primary: list[str] = []
        secondary: list[str] = []
        for source, bucket in ((headings, primary), (body, secondary)):
            for item in source:
                for part in re.split(r"[，。、；：,.;:!?！？()（）\s]+", item):
                    part = part.strip()
                    if not 2 <= len(part) <= 14 or part in cls._STOPWORDS or part in excluded:
                        continue
                    # 代码/OCR 噪声：含符号、中英混排数字、下标等
                    if re.search(r"[>=<_#|&~^$@]", part):
                        continue
                    if re.search(r"[\u4e00-\u9fff].*\d|\d.*[\u4e00-\u9fff]", part):
                        continue
                    if not (re.search(r"[一-龥]", part) or (part.isascii() and part.isalpha() and part.isupper())):
                        continue
                    # 含谓语的叙述句不是知识点，仅在标题不足时兜底
                    if re.search(r"(发生在|存放在|用于|依赖|需要|产生|进行|被固定为|可以|应该|创建|返回|转换|指定|包含|插入|连续|不再|掌握|理解)", part):
                        secondary.append(part)
                    else:
                        bucket.append(part)
        return list(dict.fromkeys(primary + secondary))[:limit]

    @classmethod
    def _mock_response(cls, system_prompt: str, user_prompt: str) -> str:
        title = cls._prompt_line(user_prompt, "课程") or "本课程"

        if "教师资料编辑助手" in system_prompt:
            current = cls._prompt_block(user_prompt, "当前资料")
            return re.sub(r"\n{3,}", "\n\n", current).strip()

        if "课程内容分析专家" in system_prompt:
            points_text = cls._prompt_line(user_prompt, "候选知识点")
            if points_text:
                terms = [p.strip() for p in re.split(r"[；;、，,]", points_text) if p.strip()][:8]
            else:
                terms = cls._salient_terms(cls._prompt_block(user_prompt, "材料"), 8, exclude=title)
            key = terms[:3] or ["核心概念与基本方法"]
            extra = [item for item in terms[3:] if len(item) <= 12]
            hard = [f"{key[0]}与{key[-1]}的区分与联系"] if len(key) > 1 else []
            hard.append(f"{extra[0]}的适用条件判断" if extra else f"{key[0]}向综合问题的迁移应用")
            note = cls._prompt_line(user_prompt, "补充说明")
            summary = (
                f"《{title}》的材料覆盖{'、'.join(terms[:4]) or '核心概念与方法'}等内容，"
                f"需要按“概念理解 → 方法应用 → 迁移反思”的顺序组织，帮助学生把{key[0]}与后续内容连成知识链。"
            )
            if note and note != "无":
                summary += f"结合补充说明（{note}），讲授应优先服务该诉求。"
            return json.dumps(
                {
                    "summary": summary,
                    "key_points": key,
                    "difficult_points": hard,
                    "prerequisites": [f"与{key[0]}相关的基础概念", "基本的分析与表达能力"],
                    "learner_misconceptions": [
                        f"把{key[0]}的结论当作普适规律，忽略成立条件",
                        f"混淆{key[0]}与{key[-1]}的适用范围" if len(key) > 1 else f"记住{key[0]}的结论却说不清依据",
                    ],
                },
                ensure_ascii=False,
            )
        if "教学设计教师" in system_prompt:
            points_text = cls._prompt_line(user_prompt, "候选知识点")
            if points_text:
                terms = [p.strip() for p in re.split(r"[；;、，,]", points_text) if p.strip()][:6]
            else:
                analysis_text = cls._prompt_block(user_prompt, "内容分析")
                key_points = re.findall(r'"key_points"\s*:\s*\[([^\]]*)\]', analysis_text)
                if key_points:
                    terms = [p.strip().strip('"') for p in key_points[0].split(",") if p.strip()][:6]
                else:
                    terms = cls._salient_terms(analysis_text, 6, exclude=title)
            focus = terms[0] if terms else "核心概念"
            second = terms[1] if len(terms) > 1 else "典型应用"
            third = terms[2] if len(terms) > 2 else second
            return json.dumps(
                {
                    "learning_objectives": [
                        f"掌握{focus}的概念、用法与适用条件",
                        f"能运用{second}完成典型应用任务",
                        "识别常见误区并完成知识迁移",
                    ],
                    "stages": [
                        {"name": "情境导入", "purpose": "激活先备知识", "activity": f"围绕{focus}的真实问题与快速诊断", "minutes": 8},
                        {"name": "重点讲授", "purpose": "建立知识结构", "activity": f"{focus}的概念讲解、示例与对比", "minutes": 22},
                        {"name": "分层探究", "purpose": "突破认知难点", "activity": f"针对{second}的分层提问与教师追问", "minutes": 12},
                        {"name": "评价总结", "purpose": "检验目标达成", "activity": "形成性评价与迁移任务", "minutes": 8},
                    ],
                    "strategies": ["问题驱动", "分层提问", "对比辨析", "即时反馈"],
                    "assessment": [f"{focus}表述的准确性", "典型任务完成质量", "迁移问题的解释质量"],
                    "exercises": [
                        {"level": "low", "question": f"用自己的话说一说{focus}的含义，并举一个例子。", "answer": f"答案要点：先给出{focus}的定义，再结合教材示例说明其特点与适用条件。"},
                        {"level": "medium", "question": f"运用{focus}与{second}完成一道典型练习，并写出关键步骤。", "answer": f"答案要点：先识别题目涉及的知识点（{focus}、{second}），再按步骤求解并检查条件是否满足。"},
                        {"level": "high", "question": f"如果改变{focus}的一个前提条件，结论还成立吗？请举例说明。", "answer": f"答案要点：指出被改变的条件，分析其对结论的影响，并给出成立或不成立的反例。"},
                    ],
                },
                ensure_ascii=False,
            )
        if "只提出一个具体" in system_prompt:
            # 本轮重点是权威来源；讲授稿是散文，抽词会误取开场白
            topic = cls._prompt_line(user_prompt, "本轮重点") or title
            other = cls._prompt_line(user_prompt, "对照知识点") or "它的适用条件"
            if "拓展型" in system_prompt:
                return f"老师，如果改变{topic}成立的关键条件，结论还成立吗？能不能举一个{topic}不适用的反例？"
            if "进阶型" in system_prompt:
                return f"老师，从{topic}推导到{other}的过程中，最容易被忽略的中间环节是哪一步？"
            return f"老师，我还分不清{topic}和{other}，判断的时候应该先看哪个条件？"
        if "逐一回应不同层次学生" in system_prompt:
            topic = cls._prompt_line(user_prompt, "本轮重点") or title
            other = cls._prompt_line(user_prompt, "对照知识点") or "它的适用条件"
            return (
                f"三个问题分别指向{topic}的辨析、推导过程和适用边界。\n\n"
                f"先回答基础问题：区分{topic}和{other}时，先确认研究对象和前提条件，再选择对应概念，两者的差别正体现在条件上。\n\n"
                f"关于推导过程：要把已知条件、使用依据和结论逐项对应，{topic}中最容易跳过的是条件校验这一步。\n\n"
                f"关于反例：只要改变{topic}的一个必要条件，原结论就可能失效。\n\n"
                f"请大家用“条件 - 方法 - 结论”这条线索，重新检查刚才关于{topic}的例子。"
            )
        if "面向课堂" in system_prompt:
            round_match = re.search(r"第\s*(\d+)\s*轮重点[：:]\s*(.*)", user_prompt)
            focus = (round_match.group(2).strip() if round_match else "") or title
            review = cls._prompt_block(user_prompt, "上轮督导")
            points_text = cls._prompt_line(user_prompt, "候选知识点")
            candidates = [p.strip() for p in re.split(r"[；;、，,]", points_text) if p.strip()] if points_text else []
            example = next((item for item in candidates if item and item != focus), "")
            if not example:
                terms = cls._salient_terms(cls._prompt_block(user_prompt, "材料依据"), 5, exclude=title)
                example = next((item for item in terms if item != focus), "课程中的典型情形")
            opening = f"这一节我们把重点放在{focus}上。"
            if review and review != "首轮，无":
                opening += "按照上一轮督导的建议，我会把成立条件讲得更明确，并留出可观察的学习产出。"
            return (
                f"{opening}\n\n"
                f"先看它要解决的问题：面对材料时不要急着套结论，第一步是识别对象与条件。"
                f"{focus}可以理解为一个判断框架——它规定了关注什么、依据什么，以及结论在什么范围内成立。\n\n"
                f"举个例子，把{focus}放到{example}的情境里：条件齐备时结论成立；一旦去掉其中一个必要条件，"
                f"结论就可能失效。这正是我们要强调概念边界的原因。\n\n"
                f"现在请大家检查：在刚才{example}的例子中，哪个条件不可缺少？如果去掉它，关于{focus}的推理还成立吗？"
            )
        if "JSON" in system_prompt and "任务" in system_prompt:
            return json.dumps(
                {
                    "acceptance_criteria": ["结论回应目标", "关键判断有依据", "建议可执行"],
                    "tasks": [],
                },
                ensure_ascii=False,
            )
        label = system_prompt.split("。", 1)[0].replace("你是", "").strip()
        excerpt = re.sub(r"\s+", " ", user_prompt)[:220]
        return (
            f"### {label}产出\n\n"
            f"围绕当前任务，我先确认了目标、限制条件与可验证结果。输入重点为：{excerpt}。\n\n"
            "- 核心判断：应先建立明确的成功标准，再按证据强度排序行动。\n"
            "- 关键风险：信息缺口、隐含依赖和缺少反例验证会削弱结论。\n"
            "- 建议动作：记录假设，补齐高影响证据，并为每项建议指定验证方式。"
        )
