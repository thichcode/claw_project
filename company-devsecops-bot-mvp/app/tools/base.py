from __future__ import annotations

from abc import ABC, abstractmethod


class Tool(ABC):
    name: str

    @abstractmethod
    async def execute(self, payload: dict) -> dict:
        raise NotImplementedError
