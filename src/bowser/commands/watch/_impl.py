import logging
import os
from collections.abc import Collection
from pathlib import Path
from threading import Condition

from reactivex import operators as ops
from reactivex.abc import DisposableBase, ObserverBase
from reactivex.scheduler import ThreadPoolScheduler
from watchdog.events import FileCreatedEvent
from watchdog.observers import Observer as FileSystemEventLoop

from ...backends.base import BowserBackend
from ...extensions.watchdog import WatchdogEventObservable
from ._preempt import PreemptObservable
from ._strategy import WatchStrategy

LOGGER = logging.getLogger("bowser")


class Terminus(ObserverBase[FileCreatedEvent], DisposableBase):
    def __init__(
        self, backends: Collection[BowserBackend], on_dispose: Condition
    ) -> None:
        self._on_dispose = on_dispose
        self._backends: Collection[BowserBackend] = backends

    def on_completed(self) -> None:
        self.dispose()

    def on_error(self, error: Exception) -> None:
        LOGGER.error("Unhandled exception in upstream Observable.", exc_info=error)
        self.dispose()

    def on_next(self, event: FileCreatedEvent) -> None:
        src = event.src_path
        if isinstance(src, bytes):
            src = src.decode("utf-8")
        if (as_path := Path(src)).name == ".bowser.ready":
            for backend in self._backends:
                try:
                    backend.upload(as_path.parent)
                except Exception:
                    LOGGER.exception(
                        "Unhandled exception in upload for backend '%s'",
                        backend.__class__.__name__,
                    )
                    LOGGER.info(
                        "Will attempt other backends (if any) and continue processing events..."
                    )

    def dispose(self) -> None:
        with self._on_dispose:
            self._on_dispose.notify_all()


def execute(
    root: Path,
    backends: Collection[BowserBackend],
    transform: WatchStrategy,
    preempt_sentinel: Path,
) -> None:
    cpus = os.cpu_count() or 1
    workers = max(cpus, 1)
    scheduler = ThreadPoolScheduler(max_workers=workers)

    completed = Condition()
    origin = WatchdogEventObservable()
    terminus = Terminus(backends, on_dispose=completed)

    origin.pipe(
        ops.subscribe_on(scheduler),
        ops.observe_on(scheduler),
        PreemptObservable(sentinel=preempt_sentinel),
        transform,
    ).subscribe(terminus)

    loop = FileSystemEventLoop()
    loop.schedule(origin, str(root), recursive=True)
    loop.start()

    # wait on the main thread until Terminus has been disposed of
    with completed:
        completed.wait()

    loop.stop()
    loop.join()
