"""LangGraph ReAct agent that orchestrates Feast operations."""

from __future__ import annotations

import warnings
from typing import Any, Dict, Optional

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

warnings.filterwarnings("ignore", message="create_react_agent", category=DeprecationWarning)
from langgraph.prebuilt import create_react_agent  # noqa: E402

from feast_agent.config import AgentConfig
from feast_agent.prompts import SYSTEM_PROMPT
from feast_agent.tools import get_all_tools


def create_agent(
    repo_path: str = ".",
    config: Optional[AgentConfig] = None,
    *,
    thread_id: str = "default",
):
    """Create a Feast Agent.

    Returns a callable agent that accepts a user message string and returns
    the assistant's response string.

    Args:
        repo_path: Path to the Feast feature repository.
        config: Optional AgentConfig; built from env vars if not provided.
        thread_id: Conversation thread ID for stateful sessions.
    """
    if config is None:
        config = AgentConfig(repo_path=repo_path)

    store = config.build_feature_store()
    llm = config.build_chat_model()
    tools = get_all_tools(store)
    checkpointer = MemorySaver()

    graph = create_react_agent(
        model=llm,
        tools=tools,
        prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
    )

    class FeastAgent:
        """Thin wrapper providing a simple invoke(message) -> response API."""

        def __init__(self):
            self.graph = graph
            self.thread_id = thread_id
            self.store = store

        def invoke(self, message: str) -> str:
            """Send a message and return the agent's text response."""
            result = self.graph.invoke(
                {"messages": [HumanMessage(content=message)]},
                config={"configurable": {"thread_id": self.thread_id}},
            )
            messages = result.get("messages", [])
            for msg in reversed(messages):
                if isinstance(msg, AIMessage) and msg.content:
                    return msg.content
            return "(No response from agent)"

        async def ainvoke(self, message: str) -> str:
            """Async version of invoke."""
            result = await self.graph.ainvoke(
                {"messages": [HumanMessage(content=message)]},
                config={"configurable": {"thread_id": self.thread_id}},
            )
            messages = result.get("messages", [])
            for msg in reversed(messages):
                if isinstance(msg, AIMessage) and msg.content:
                    return msg.content
            return "(No response from agent)"

        def stream_events(self, message: str):
            """Stream with visibility into tool calls.

            Uses default stream mode for broad LangGraph compatibility.

            Yields ``(kind, payload)`` tuples:

            - ``("tool_start", {"name": str, "args": dict})``
            - ``("tool_end", {"name": str, "result": str})``
            - ``("response", str)``  — final text answer (may arrive in one chunk)
            """
            from langchain_core.messages import ToolMessage

            for chunk in self.graph.stream(
                {"messages": [HumanMessage(content=message)]},
                config={"configurable": {"thread_id": self.thread_id}},
            ):
                for node_name, node_output in chunk.items():
                    msgs = node_output.get("messages", [])
                    for msg in msgs:
                        if isinstance(msg, AIMessage):
                            if msg.tool_calls:
                                for tc in msg.tool_calls:
                                    yield ("tool_start", {
                                        "name": tc["name"],
                                        "args": tc.get("args", {}),
                                    })
                            if msg.content:
                                yield ("response", msg.content)
                        elif isinstance(msg, ToolMessage):
                            yield ("tool_end", {
                                "name": msg.name or "",
                                "result": msg.content or "",
                            })

    return FeastAgent()
