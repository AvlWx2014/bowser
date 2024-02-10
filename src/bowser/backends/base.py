from abc import ABC, abstractmethod
from pathlib import Path


class BowserBackend(ABC):
    @abstractmethod
    def sync(self, source: Path) -> None:
        """Perform a `sync` operation between ``source`` and this backend."""
