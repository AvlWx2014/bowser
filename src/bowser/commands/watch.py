import logging
from collections.abc import Callable, Collection
from concurrent.futures import Executor, as_completed
from pathlib import Path
from time import sleep

from ..backends.base import BowserBackend
from .di import provide_Executor

_Callback = Callable[[], None]
_ActionWithCallback = Callable[[Path, _Callback], None]


def _async_multicall(
    backends: Collection[BowserBackend],
    source: Path,
    executor: Executor | None = None,
    callback: Callable[[], None] | None = None,
):
    if executor is None:
        executor = provide_Executor()

    futures = [executor.submit(backend.sync, source) for backend in backends]
    for future in as_completed(futures):
        if (exception := future.exception()) is not None:
            logging.error("Exception in backend sync operation\n%s", exception)

    if callback is not None:
        callback()


def execute(
    polling_interval: int,
    root: Path,
    backends: Collection[BowserBackend],
) -> None:
    executor = provide_Executor()

    # adapter from async_multicall to type (Path, () -> None) -> None
    # functools.partial doesn't seem to work here for two reasons:
    # 1. the arguments that need partial application are not contiguous. normally you can just use
    #   keyword arguments for this, but...
    # 2. all the FileSystemWatcher knows is that `action` is a function of type
    #   (Path, () -> None) -> None, so it can't use keyword arguments like `callback=...`
    def _action(source: Path, callback: Callable[[], None]) -> None:
        nonlocal backends, executor
        _async_multicall(backends, source, executor, callback)

    watcher = FileSystemWatcher(action=_action)
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
