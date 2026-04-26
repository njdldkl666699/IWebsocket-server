"""Shared runtime objects for the LangGraph API process."""

from __future__ import annotations

from .phone_gateway import DeviceGateway
from .system_gateway import SystemToolGateway

phone_gateway = DeviceGateway()
system_gateway = SystemToolGateway()

__all__ = ["phone_gateway", "system_gateway"]
