"""Base class for chaos tests."""
from __future__ import annotations

from abc import ABC, abstractmethod


class ChaosTest(ABC):
    """A reproducible failure-mode injection.

    Each test:
      1. setup() — capture pre-state for restore
      2. induce() — apply chaos action + any load
      3. teardown() — restore pre-state. ALWAYS runs (try/finally in runner).

    The runner polls /decisions for a row matching `expected_alertname`
    after `induce()` returns, then renders the captured RCA + scores into
    the chaos report.
    """

    name: str = "<unnamed>"
    description: str = ""
    expected_alertname: str = ""
    timeout_s: int = 600

    @abstractmethod
    async def setup(self) -> None: ...

    @abstractmethod
    async def induce(self) -> None: ...

    @abstractmethod
    async def teardown(self) -> None: ...
