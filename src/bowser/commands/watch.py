import logging
from collections.abc import Callable, Collection
from pathlib import Path
from time import sleep

from ..backends.base import BowserBackend

_ActionWithCallback = Callable[[Path, Callable[[], None]], None]


def execute(
    polling_interval: int,
    root: Path,
    backends: Collection[BowserBackend],
) -> None:
    def _multicall_sync(source: Path, callback: Callable[[], None] | None = None):
        # nonlocal is not strictly necessary here since we're not
        # assigning anything to the name, but it helps signal explicitly
        # that 'backends' is a member of this closure
        nonlocal backends

        for backend in backends:
            backend.sync(source)

        if callback is not None:
            callback()

    watcher = FileSystemWatcher(action=_multicall_sync)
    watcher.watch(root, polling_interval)


class FileSystemWatcher:

    def __init__(self, action: _ActionWithCallback) -> None:
        self._ready_sentinel = Path(".bowser.ready")
        self._complete_sentinel = Path(".bowser.complete")
        self._action: _ActionWithCallback = action

    def watch(self, root: Path, polling_interval: int):
        logging.info("Watching %s for subtrees ready for sync", root)
        while True:
            for subtree in filter(lambda node: node.is_dir(), root.iterdir()):
                complete = subtree / self._complete_sentinel
                if complete.exists():
                    continue
                logging.debug("Checking %s", subtree)
                ready = subtree / self._ready_sentinel
                if ready.exists():
                    logging.info("Found tree ready for sync: %s", subtree)
                    self._action(subtree, complete.touch)
                    logging.info("Sync of %s complete.", subtree)
            stop_sentinel = root / self._complete_sentinel
            if stop_sentinel.exists():
                logging.info("All operations signaled complete.")
                break
            sleep(polling_interval)
