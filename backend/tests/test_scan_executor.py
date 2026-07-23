"""Dedicated scan pool must exist and stay separate from default executor."""
from __future__ import annotations

import inspect

import routes.health as health_routes
from scan_executor import get_scan_executor, shutdown_scan_executor


def test_scan_executor_singleton():
    shutdown_scan_executor()
    a = get_scan_executor()
    b = get_scan_executor()
    assert a is b
    shutdown_scan_executor()


def test_health_route_is_async_liveness():
    """Sync health would share the default pool with IBKR bridge waits."""
    assert inspect.iscoroutinefunction(health_routes.health_check)
