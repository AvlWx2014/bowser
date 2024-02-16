from abc import ABC, abstractmethod
from pathlib import Path

from ._event import Event


class WatchStrategy(ABC):
    def __init__(self, watch_root: Path) -> None:
        self._root = watch_root

    @abstractmethod
    def on_next(self, event: Event) -> None: ...

    @abstractmethod
    def should_stop(self) -> bool: ...


class SentinelWatchStrategy(WatchStrategy):

    def __init__(self, watch_root: Path, *, sentinel: str = ".bowser.complete") -> None:
        super().__init__(watch_root)
        self._sentinel = sentinel

    def on_next(self, event: Event) -> None:
        pass

    def should_stop(self) -> bool:
        return (self._root / self._sentinel).exists()


class CountWatchStrategy(WatchStrategy):
    def __init__(self, watch_root: Path, *, limit: int) -> None:
        super().__init__(watch_root)
        self._limit = limit
        self._count = 0

    def on_next(self, event: Event) -> None:
        match event:
            case Event.COMPLETION:
                if self._count < self._limit:
                    self._count += 1
            case _:
                raise RuntimeError(
                    "Exhaustive match on enum type 'Event' failed to match."
                    f"Unknown value: {event}"
                )

    def should_stop(self) -> bool:
        return self._count == self._limit
