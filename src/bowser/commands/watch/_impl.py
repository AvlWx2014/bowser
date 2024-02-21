import logging
import os
from collections.abc import Collection
from pathlib import Path
from threading import Condition

from reactivex import operators as ops
from reactivex.abc import DisposableBase, ObserverBase
from reactivex.scheduler import EventLoopScheduler, ThreadPoolScheduler

from ...backends.base import BowserBackend
from ...inotify import InotifyEvent, InotifyEventData, observable_inotifywait
from ._strategy import WatchStrategy

LOGGER = logging.getLogger("bowser")


def execute(
    root: Path,
    backends: Collection[BowserBackend],
    transform: WatchStrategy,
):
    completed = Condition()

    class AnonymousObserver(ObserverBase[InotifyEventData], DisposableBase):

        def on_next(self, value: InotifyEventData) -> None:
            nonlocal backends
            if InotifyEvent.CREATE not in value.events:
                return

            if value.subject == ".bowser.ready":
                for backend in backends:
                    try:
                        backend.upload(value.watch)
                    except Exception:
                        LOGGER.exception("Unhandled exception in backend upload.")
                        LOGGER.info("Observer will continue processing events...")

        def on_error(self, error: Exception) -> None:
            LOGGER.error("Unhandled exception in upstream Observable.", exc_info=error)
            self.dispose()

        def on_completed(self) -> None:
            self.dispose()

        def dispose(self) -> None:
            with completed:
                completed.notify()

    cpus = os.cpu_count() or 1
    workers = max(cpus, 1)
    scheduler = ThreadPoolScheduler(max_workers=workers)
    (
        # wrap the source Observable in our watch strategy transformer
        transform(
            # run the source observable work on the EventLoopScheduler
            observable_inotifywait(root, scheduler=EventLoopScheduler())
        )
        .pipe(
            # run the observer actions on the ThreadPoolScheduler
            ops.observe_on(scheduler),
        )
        .subscribe(AnonymousObserver())
    )
    # wait on the main thread until the Observer has been notified of
    # the upstream completion event (i.e. that on_completed has been called)
    with completed:
        completed.wait()
