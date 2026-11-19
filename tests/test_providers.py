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


RESPONSES_MODELS = ["gpt-5.6", "gpt-5.6-sol", "gpt-5.6-pro", "gpt-6", "gpt-6-luna", "gpt-6.2", "gpt-6.2-sol"]


async def _chat_kwargs(model_name, **chat_kwargs):
    model = GPTModel(model=model_name)
    with patch("src.providers.base.acompletion", new_callable=AsyncMock) as completion:
        completion.return_value = _chat_response()
        response = await model.chat([{"role": "user", "content": "hello"}], **chat_kwargs)
    return completion.await_args.kwargs, response


@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", RESPONSES_MODELS)
async def test_chat_routes_newer_gpt_models_through_responses_api(model_name):
    kwargs, _ = await _chat_kwargs(model_name, tools=[TOOL])

    assert kwargs["model"] == f"openai/responses/{model_name}"
    assert kwargs["reasoning_effort"] == "low"
    assert kwargs["store"] is False
    assert kwargs["text"] == {"verbosity": "low"}
    assert kwargs["tools"] == [TOOL]
    # litellm's drop_params would otherwise strip these for gpt-6 names
    assert kwargs["allowed_openai_params"] == ["reasoning_effort", "store"]
    assert "verbosity" not in kwargs


@pytest.mark.asyncio
async def test_chat_uses_low_reasoning_without_tools_too():
    kwargs, _ = await _chat_kwargs("gpt-6.2-sol")

    assert kwargs["reasoning_effort"] == "low"
    assert "tools" not in kwargs


@pytest.mark.asyncio
async def test_chat_json_mode_on_responses_api_keeps_verbosity_and_format_together():
    kwargs, _ = await _chat_kwargs("gpt-6.2-sol", json_mode=True)

    assert kwargs["text"] == {"verbosity": "low", "format": {"type": "json_object"}}
    assert "response_format" not in kwargs


@pytest.mark.asyncio
async def test_chat_leaves_older_openai_models_on_chat_completions():
    kwargs, _ = await _chat_kwargs("gpt-4o-mini", tools=[TOOL], json_mode=True)

    assert kwargs["model"] == "openai/gpt-4o-mini"
    assert kwargs["verbosity"] == "low"
    assert kwargs["response_format"] == {"type": "json_object"}
    assert "reasoning_effort" not in kwargs
    assert "allowed_openai_params" not in kwargs
    assert "text" not in kwargs


@pytest.mark.asyncio
async def test_chat_finds_tool_calls_split_into_a_separate_choice():
    """The Responses API bridge puts preamble text and tool calls in separate choices."""
    tool_call = SimpleNamespace(function=SimpleNamespace(arguments="{}"))
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="Let me check.", tool_calls=None)),
            SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[tool_call])),
        ],
        usage=SimpleNamespace(total_tokens=10, completion_tokens=4),
        _hidden_params={"response_cost": 0.001},
    )
    model = GPTModel(model="gpt-6.2-sol")
    with patch("src.providers.base.acompletion", new_callable=AsyncMock) as completion:
        completion.return_value = response
        result = await model.chat([{"role": "user", "content": "hello"}], tools=[TOOL])

    assert result.message == "Let me check."
    assert result.tool_calls == [tool_call]


@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", ["gpt-5.60", "gpt-60"])
async def test_chat_does_not_match_longer_version_numbers(model_name):
    model = GPTModel(model=model_name)

    with patch("src.providers.base.acompletion", new_callable=AsyncMock) as completion:
        completion.return_value = _chat_response()
        await model.chat([{"role": "user", "content": "hello"}], tools=[TOOL])

    assert completion.await_args.kwargs["model"] == f"openai/{model_name}"
    assert "reasoning_effort" not in completion.await_args.kwargs


@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", ["gpt-5.6-sol", "gpt-6-luna", "gpt-6.2-sol"])
async def test_function_call_disables_reasoning(model_name):
    model = GPTModel(model=model_name)

    with patch("src.providers.base.acompletion", new_callable=AsyncMock) as completion:
        completion.return_value = _chat_response('{"value": 42}')
        response = await model.function_call(
            [{"role": "user", "content": "hello"}],
            tools=[TOOL],
        )

    assert completion.await_args.kwargs["reasoning_effort"] == "none"
    assert completion.await_args.kwargs["allowed_openai_params"] == ["reasoning_effort"]
    assert response.parameters == {"value": 42}
