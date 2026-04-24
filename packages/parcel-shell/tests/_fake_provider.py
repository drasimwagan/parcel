"""Shared fake :class:`ClaudeProvider` for orchestrator and HTTP tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from parcel_shell.ai.provider import GeneratedFiles


@dataclass
class FakeProvider:
    """Hands out scripted responses in order.

    Each queue item is one of:
      - ``GeneratedFiles`` (returned as-is)
      - ``dict[str, bytes]`` (wrapped into ``GeneratedFiles``)
      - an ``Exception`` (raised)
    """

    queue: list = field(default_factory=list)

    async def generate(self, prompt, working_dir, *, prior=None):  # noqa: ARG002
        if not self.queue:
            raise RuntimeError("FakeProvider queue exhausted")
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, GeneratedFiles):
            return item
        return GeneratedFiles(files=item, transcript="fake")
