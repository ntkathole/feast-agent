"""Feast Agent — LLM-powered feature store management."""

from feast_agent.agent import create_agent
from feast_agent.config import AgentConfig

__all__ = ["create_agent", "AgentConfig"]
__version__ = "0.1.0"
