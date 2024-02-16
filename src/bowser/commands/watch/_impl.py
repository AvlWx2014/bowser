import logging
from collections.abc import Callable, Collection
from concurrent.futures import Executor, as_completed
from pathlib import Path
from time import sleep

from ...backends.base import BowserBackend
from ..di import provide_Executor
from ._event import Event
from ._strategy import WatchStrategy

_Callback = Callable[[], None]
_AsyncAction = Callable[[Path, _Callback], None]


LOGGER = logging.getLogger("bowser")


def _async_multicall(
    backends: Collection[BowserBackend],
    source: Path,
    executor: Executor | None = None,
    callback: Callable[[], None] | None = None,
) -> None:
    if executor is None:
        executor = provide_Executor()

    futures = [executor.submit(backend.upload, source) for backend in backends]
    for future in as_completed(futures):
        if (exception := future.exception()) is not None:
            LOGGER.error("Exception in backend sync operation\n%s", exception)

    if callback is not None:
        callback()

    LOGGER.debug("Backend operation complete.")


def execute(
    root: Path,
    polling_interval: int,
    backends: Collection[BowserBackend],
    strategy: WatchStrategy,
    executor: Executor,
) -> None:
    # adapter from async_multicall to type (Path, () -> None) -> None
    # functools.partial doesn't seem to work here for two reasons:
    # 1. the arguments that need partial application are not contiguous. normally you can just use
    #   keyword arguments for this, but...
    # 2. all the FileSystemWatcher knows is that `action` is a function of type
    #   (Path, () -> None) -> None, so it can't use keyword arguments like `callback=...`
    #   without being fragile.
    def _action(source: Path, callback: Callable[[], None]) -> None:
        nonlocal backends, executor
        _async_multicall(backends, source, executor, callback)

    watcher = FileSystemWatcher(action=_action, strategy=strategy)
    watcher.watch(root, polling_interval)


class FileSystemWatcher:

    def __init__(self, action: _AsyncAction, strategy: WatchStrategy) -> None:
        self._ready_sentinel = Path(".bowser.ready")
        self._complete_sentinel = Path(".bowser.complete")
        self._action: _AsyncAction = action
        self._strategy: WatchStrategy = strategy

    def watch(self, root: Path, polling_interval: int) -> None:
        LOGGER.info("Watching %s for subtrees marked ready...", root)
        stop = False
        while True:
            for subtree in filter(lambda node: node.is_dir(), root.iterdir()):
                complete = subtree / self._complete_sentinel
                if complete.exists():
                    continue
                LOGGER.debug("Checking %s", subtree)
                ready = subtree / self._ready_sentinel
                if ready.exists():
                    LOGGER.info("Subtree ready: %s", subtree)
                    self._action(subtree, complete.touch)
                    self._strategy.on_next(Event.COMPLETION)
                if self._strategy.should_stop():
                    stop = True
                    break
            if stop:
                LOGGER.info("All operations signaled complete.")
                break
            sleep(polling_interval)
