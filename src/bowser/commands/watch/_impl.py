import logging
import os
from collections.abc import Callable, Collection
from pathlib import Path
from threading import Condition
from typing import cast

from reactivex import Observable
from reactivex import operators as ops
from reactivex.abc import DisposableBase, ObserverBase
from reactivex.scheduler import ThreadPoolScheduler
from watchdog.events import FileCreatedEvent, FileSystemEventHandler
from watchdog.observers import Observer as FileSystemEventLoop

from ...backends.base import BowserBackend
from ...extensions.watchdog import ReplayEventsObservable, WatchdogEventObservable
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
    on_start: Callable[[], None] | None = None,
) -> None:
    cpus = os.cpu_count() or 1
    workers = max(cpus, 1)
    scheduler = ThreadPoolScheduler(max_workers=workers)

    completed = Event()
    realtime: Observable[FileCreatedEvent] = WatchdogEventObservable()
    replay: Observable[FileCreatedEvent] = ReplayEventsObservable(root=root)
    origin: Observable[FileCreatedEvent] = realtime.pipe(ops.merge(replay))
    terminus = Terminus(backends, on_dispose=completed)

    origin.pipe(
        ops.subscribe_on(scheduler),
        ops.observe_on(scheduler),
        PreemptObservable(sentinel=preempt_sentinel),
        # Ignore: Mypy attr-defined
        # Reason: In this form, mypy complains that the lambda parameter is
        #  type _T and thus does not have enough information to infer the
        #  presence of the attribute "src_path", but if I add an explicit
        #  cast(FileCreatedEvent, it).src_path it complains about an unnecessary
        #  cast to FileCreatedEvent.
        ops.distinct(lambda it: it.src_path),  # type: ignore[attr-defined]
        transform,
    ).subscribe(terminus)

    # TODO: might make sense to move this to the WatchdogEventObservable
    #  and have it start the loop on subscribe, and stop the loop on completion
    #  or disposal.
    loop = FileSystemEventLoop()
    loop.schedule(cast(FileSystemEventHandler, realtime), str(root), recursive=True)
    loop.start()

    if on_start is not None:
        on_start()

    # wait on the main thread until Terminus has been disposed of
    with completed:
        completed.wait()

    loop.stop()
    loop.join()
