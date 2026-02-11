"""
Tests for src/tools/handlers.py
"""

import pytest
from src.tools.handlers import ToolDispatcher, ToolResult


class TestToolResult:
    """Tests for ToolResult dataclass."""

    def test_default_values(self):
        result = ToolResult(handled=True)
        assert result.handled is True
        assert result.needs_followup is False
        assert result.followup_data is None

    def test_with_followup(self):
        result = ToolResult(handled=True, needs_followup=True, followup_data={"key": "value"})
        assert result.handled is True
        assert result.needs_followup is True
        assert result.followup_data == {"key": "value"}


class TestToolDispatcher:
    """Tests for ToolDispatcher class."""

    def test_register_and_dispatch(self):
        """Registered handlers should be callable."""
        dispatcher = ToolDispatcher()
        call_log = []

        async def mock_handler(msg, **args):
            call_log.append({"msg": msg, "args": args})

        dispatcher.register("test_tool", mock_handler)

        # Can't test async directly without running in event loop
        assert "test_tool" in dispatcher.registered_tools

    def test_registered_tools_property(self):
        """Should list all registered tool names."""
        dispatcher = ToolDispatcher()

        async def mock_handler(msg, **args):
            pass

        dispatcher.register("tool1", mock_handler)
        dispatcher.register("tool2", mock_handler)

        assert set(dispatcher.registered_tools) == {"tool1", "tool2"}

    def test_register_special(self):
        """Special handlers should be tracked separately."""
        dispatcher = ToolDispatcher()

        async def special_handler(msg, args, context):
            return ToolResult(handled=True)

        dispatcher.register_special("special_tool", special_handler)

        assert "special_tool" in dispatcher.registered_tools


@pytest.mark.asyncio
class TestToolDispatcherAsync:
    """Async tests for ToolDispatcher."""

    async def test_dispatch_calls_handler(self):
        """Dispatch should call the registered handler."""
        dispatcher = ToolDispatcher()
        call_log = []

        async def mock_handler(msg, **args):
            call_log.append({"msg": msg, "args": args})

        dispatcher.register("test_tool", mock_handler)

        result = await dispatcher.dispatch("test_tool", {"key": "value"}, "test_message")

        assert result.handled is True
        assert len(call_log) == 1
        assert call_log[0]["msg"] == "test_message"
        assert call_log[0]["args"] == {"key": "value"}

    async def test_dispatch_unknown_tool(self):
        """Dispatching unknown tool should return handled=False."""
        dispatcher = ToolDispatcher()

        result = await dispatcher.dispatch("unknown_tool", {}, "test_message")

        assert result.handled is False

    async def test_dispatch_special_handler(self):
        """Special handlers should receive context."""
        dispatcher = ToolDispatcher()
        received_context = None

        async def special_handler(msg, args, context):
            nonlocal received_context
            received_context = context
            return ToolResult(handled=True, followup_data="special_result")

        dispatcher.register_special("special_tool", special_handler)

        result = await dispatcher.dispatch(
            "special_tool",
            {"arg": "value"},
            "test_message",
            context={"extra": "context"}
        )

        assert result.handled is True
        assert result.followup_data == "special_result"
        assert received_context == {"extra": "context"}


class TestManageMemoriesTool:
    """Tests for manage_memories tool definition."""

    def test_tool_definition_structure(self):
        """manage_memories tool should have correct structure."""
        from src.tools.definitions import manage_memories_tool
        func = manage_memories_tool['function']
        assert func['name'] == 'manage_memories'
        assert 'action' in func['parameters']['properties']
        assert func['parameters']['properties']['action']['enum'] == ['list', 'delete_one', 'delete_all']
        assert 'memory_id' in func['parameters']['properties']
        assert func['parameters']['required'] == ['action']
