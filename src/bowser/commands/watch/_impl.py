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
            LOGGER.info("AnonymousObserver received event %s", value)
            if InotifyEvent.CREATE not in value.events:
                LOGGER.debug("AnonymousObserver ignoring event.")
                return

            if value.subject == ".bowser.ready":
                for backend in backends:
                    LOGGER.info("Uploading with backend %s...", backend)
                    backend.upload(value.watch)

        def on_error(self, error: Exception) -> None:
            LOGGER.error("Unhandled exception", exc_info=error)

        def on_completed(self) -> None:
            LOGGER.info("AnonymousObserver::on_completed")
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
