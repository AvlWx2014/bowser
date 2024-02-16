from collections.abc import Sequence
from enum import StrEnum, auto


class WatchType(StrEnum):
    SENTINEL = auto()
    COUNT = auto()

    @classmethod
    def values(cls) -> Sequence[str]:
        return tuple(e.value for e in cls)
