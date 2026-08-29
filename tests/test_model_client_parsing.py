import asyncio

import pytest

from backend.model_settings.models import RuntimeModelConfig
from backend.workflows.llm import ModelClient


class _StubResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _StubModel:
    def __init__(self, content: str) -> None:
        self._content = content

    async def ainvoke(self, _messages):
        return _StubResponse(self._content)


def _client_returning(content: str) -> ModelClient:
    client = ModelClient(RuntimeModelConfig(provider="mock"))
    client._model = _StubModel(content)
    return client


def test_reasoning_chain_is_stripped_from_lecture_text():
    """推理模型的 <think> 思维链不能出现在课堂记录里。"""
    raw = "<think>用户想要一段讲授稿，我先梳理结构。</think>\n同学们，今天我们学习光反应。"
    result = asyncio.run(_client_returning(raw).generate("系统", "用户"))
    assert result == "同学们，今天我们学习光反应。"
    assert "<think>" not in result


def test_unclosed_reasoning_chain_does_not_leak():
    """思维链未闭合（输出被截断）时也不应泄漏到正文。"""
    raw = "<think>我需要考虑 {a: 1} 这个结构，然后"
    result = asyncio.run(_client_returning(raw).generate("系统", "用户"))
    assert "<think>" not in result


def test_json_is_extracted_when_wrapped_in_prose_containing_braces():
    """说明性文字里出现花括号时，仍应提取到最外层完整 JSON 对象。"""
    raw = (
        "<think>格式类似 {name: ...} 的结构，我先想清楚。</think>\n"
        '这是设计结果：\n{"learning_objectives": ["解释光反应"], '
        '"stages": [{"name": "导入", "minutes": 8}]}\n以上。'
    )
    parsed = asyncio.run(_client_returning(raw).generate_json("系统", "用户"))
    assert parsed["learning_objectives"] == ["解释光反应"]
    assert parsed["stages"][0]["name"] == "导入"


def test_json_in_code_fence_is_parsed():
    raw = '```json\n{"score": 88, "dimensions": {"教学设计": 90}}\n```'
    parsed = asyncio.run(_client_returning(raw).generate_json("系统", "用户"))
    assert parsed["score"] == 88
    assert parsed["dimensions"]["教学设计"] == 90


def test_largest_json_object_wins_over_small_example_object():
    raw = (
        '格式示例：{}\n实际结果：'
        '{"score": 91, "dimensions": {"教学设计": 92}, '
        '"strengths": ["证据具体"]}'
    )

    parsed = asyncio.run(_client_returning(raw).generate_json("系统", "用户"))

    assert parsed["score"] == 91
    assert parsed["strengths"] == ["证据具体"]


def test_response_without_json_object_raises():
    with pytest.raises(ValueError):
        asyncio.run(_client_returning("模型这次没有返回 JSON。").generate_json("系统", "用户"))


def test_model_metrics_are_recorded_for_active_workflow_trace():
    async def run_test():
        client = _client_returning("这是模型输出。")
        token = client.begin_metrics_trace()
        try:
            await client.generate("系统提示", "用户材料")
            return client.metrics_since(0)
        finally:
            client.end_metrics_trace(token)

    metrics = asyncio.run(run_test())
    assert metrics["request_count"] == 1
    assert metrics["input_tokens"] > 0
    assert metrics["output_tokens"] > 0
    assert metrics["estimated"] is True
