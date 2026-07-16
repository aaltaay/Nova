"""Public runtime-state provider for scanner/application consumers."""

from runtime_state.state import (
    ScannerRuntimeConfig,
    ScannerRuntimeState,
    get_runtime_state,
    reset_runtime_state,
    set_runtime_state_for_testing,
)

__all__ = [
    "ScannerRuntimeConfig",
    "ScannerRuntimeState",
    "get_runtime_state",
    "reset_runtime_state",
    "set_runtime_state_for_testing",
]
