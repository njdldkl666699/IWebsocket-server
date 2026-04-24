"""Shared runtime objects for the LangGraph API process."""

from __future__ import annotations

from .phone_gateway import DeviceGateway

gateway = DeviceGateway()

__all__ = ["gateway"]
