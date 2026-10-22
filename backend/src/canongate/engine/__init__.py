"""Engine: auto-registering check execution and streaming runner."""

from canongate.engine.check import Check
from canongate.engine.runner import run_checks, run_checks_collect

__all__ = ["Check", "run_checks", "run_checks_collect"]
