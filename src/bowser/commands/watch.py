from collections.abc import Collection
from pathlib import Path

from ..backends.base import BowserBackend


def execute(
    polling_interval: int, root: Path, backends: Collection[BowserBackend]
) -> None:
    pass
