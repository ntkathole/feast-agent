"""LangGraph state schema for the Feast Agent."""

from __future__ import annotations

from typing import Annotated, Sequence

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState:
    """TypedDict-style state for the LangGraph agent.

    Using annotation-based reducers so LangGraph knows how to merge
    message lists across graph steps.
    """

    messages: Annotated[Sequence[BaseMessage], add_messages]
