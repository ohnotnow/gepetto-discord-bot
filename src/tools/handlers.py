"""
Tool call dispatch logic for the Discord bot.

This module provides a clean way to dispatch tool calls to their handlers,
while keeping the actual handler implementations in main.py where they have
access to the necessary globals (chatbot, bot_state, etc.).
"""

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Result of a tool call dispatch."""
    handled: bool
    needs_followup: bool = False
    followup_data: Any = None


class ToolDispatcher:
    """
    Dispatches tool calls to registered handlers.

    Usage:
        dispatcher = ToolDispatcher()
        dispatcher.register('calculate', calculate_handler)
        dispatcher.register('web_search', websearch_handler)

        result = await dispatcher.dispatch(fname, arguments, message)
    """

    def __init__(self):
        self._handlers: Dict[str, Callable] = {}
        self._special_handlers: Dict[str, Callable] = {}

    def register(self, tool_name: str, handler: Callable) -> None:
        """Register a simple handler that takes (message, **arguments)."""
        self._handlers[tool_name] = handler

    def register_special(self, tool_name: str, handler: Callable) -> None:
        """
        Register a special handler that needs additional context.
        Handler signature: async (message, arguments, context) -> ToolResult
        """
        self._special_handlers[tool_name] = handler

    async def dispatch(
        self,
        tool_name: str,
        arguments: dict,
        message,
        context: Optional[dict] = None
    ) -> ToolResult:
        """
        Dispatch a tool call to its handler.

        Returns ToolResult indicating whether the call was handled.
        """
        # Check special handlers first
        if tool_name in self._special_handlers:
            handler = self._special_handlers[tool_name]
            return await handler(message, arguments, context or {})

        # Check simple handlers
        if tool_name in self._handlers:
            handler = self._handlers[tool_name]
            await handler(message, **arguments)
            return ToolResult(handled=True)

        # Unknown tool
        logger.info(f'Unknown tool call: {tool_name}')
        return ToolResult(handled=False)

    @property
    def registered_tools(self) -> list:
        """List all registered tool names."""
        return list(self._handlers.keys()) + list(self._special_handlers.keys())
