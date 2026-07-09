"""Tests for the shared LiteLLM provider implementation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.providers.gpt import GPTModel


TOOL = {
    "type": "function",
    "function": {
        "name": "example_tool",
        "description": "An example tool",
        "parameters": {"type": "object", "properties": {}},
    },
}


def _chat_response(arguments="{}"):
    function = SimpleNamespace(arguments=arguments)
    tool_call = SimpleNamespace(function=function)
    message = SimpleNamespace(content="ok", tool_calls=[tool_call])
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(total_tokens=10, completion_tokens=4),
        _hidden_params={"response_cost": 0.001},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", ["gpt-5.6", "gpt-5.6-sol", "gpt-5.6-pro"])
async def test_chat_disables_reasoning_for_gpt_5_6_tools(model_name):
    model = GPTModel(model=model_name)

    with patch("src.providers.base.acompletion", new_callable=AsyncMock) as completion:
        completion.return_value = _chat_response()
        await model.chat([{"role": "user", "content": "hello"}], tools=[TOOL])

    assert completion.await_args.kwargs["reasoning_effort"] == "none"


@pytest.mark.asyncio
async def test_chat_does_not_disable_reasoning_without_tools():
    model = GPTModel(model="gpt-5.6-sol")

    with patch("src.providers.base.acompletion", new_callable=AsyncMock) as completion:
        completion.return_value = _chat_response()
        await model.chat([{"role": "user", "content": "hello"}])

    assert "reasoning_effort" not in completion.await_args.kwargs


@pytest.mark.asyncio
async def test_chat_does_not_disable_reasoning_for_other_models():
    model = GPTModel(model="gpt-4o-mini")

    with patch("src.providers.base.acompletion", new_callable=AsyncMock) as completion:
        completion.return_value = _chat_response()
        await model.chat([{"role": "user", "content": "hello"}], tools=[TOOL])

    assert "reasoning_effort" not in completion.await_args.kwargs


@pytest.mark.asyncio
async def test_chat_does_not_treat_gpt_5_60_as_gpt_5_6():
    model = GPTModel(model="gpt-5.60")

    with patch("src.providers.base.acompletion", new_callable=AsyncMock) as completion:
        completion.return_value = _chat_response()
        await model.chat([{"role": "user", "content": "hello"}], tools=[TOOL])

    assert "reasoning_effort" not in completion.await_args.kwargs


@pytest.mark.asyncio
async def test_function_call_disables_reasoning_for_gpt_5_6_variant():
    model = GPTModel(model="gpt-5.6-sol")

    with patch("src.providers.base.acompletion", new_callable=AsyncMock) as completion:
        completion.return_value = _chat_response('{"value": 42}')
        response = await model.function_call(
            [{"role": "user", "content": "hello"}],
            tools=[TOOL],
        )

    assert completion.await_args.kwargs["reasoning_effort"] == "none"
    assert response.parameters == {"value": 42}
