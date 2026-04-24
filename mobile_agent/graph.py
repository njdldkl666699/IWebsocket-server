"""LangGraph Server entrypoint for the Android mobile agent."""

from __future__ import annotations

from .custom_deep_agent import build_agent
from .runtime import gateway

graph = build_agent(gateway)

__all__ = ["gateway", "graph"]
