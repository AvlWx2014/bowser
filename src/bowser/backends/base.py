from abc import ABC, abstractmethod
from pathlib import Path


class BowserBackend(ABC):
    @abstractmethod
    def upload(self, source: Path) -> None:
        """Perform an 'upload' operation between ``source`` and this backend."""
