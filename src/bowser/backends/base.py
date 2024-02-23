from abc import ABC, abstractmethod
from pathlib import Path


class BowserBackend(ABC):
    def __init__(self, watch_root: Path) -> None:
        self._watch_root = watch_root

    @property
    def watch_root(self) -> Path:
        return self._watch_root

    @abstractmethod
    def upload(self, source: Path) -> None:
        """Perform an 'upload' operation between ``source`` and this backend."""
