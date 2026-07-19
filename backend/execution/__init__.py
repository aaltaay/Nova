"""Centralized trading execution path (ADR 007).

Public entry: ``from execution.service import execute``.
Strategies, agents, scripts, and UI routes must not call the broker SDK.
"""
from execution.latency import latency_summary
from execution.service import execute, get_execution

__all__ = ["execute", "get_execution", "latency_summary"]
