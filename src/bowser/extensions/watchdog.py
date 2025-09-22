import os
from pathlib import Path
from typing import Any

import reactivex as rx
from reactivex import Observable, Subject
from reactivex.abc import DisposableBase, ObserverBase, SchedulerBase
from reactivex.disposable import CompositeDisposable, Disposable
from reactivex.scheduler import CurrentThreadScheduler
from watchdog.events import DirCreatedEvent, FileCreatedEvent, FileSystemEventHandler


class WatchdogEventObservable(Subject[FileCreatedEvent], FileSystemEventHandler):
    """Observable source for file creation events from Watchdog.

    Directory creation events are filtered out since Bowser is only concerned
    with sentinel files.
    """

    def on_created(self, event: DirCreatedEvent | FileCreatedEvent) -> None:
        # TODO: create an intermediate event type that can be used by the downstream
        #   regardless of where the upstream events are coming from to avoid switching
        #   everything around again.
        match event:
            case FileCreatedEvent():
                self.on_next(event)


def ReplayEventsObservable(root: Path) -> Observable[FileCreatedEvent]:  # noqa: N802
    """Cold observable source which emits synthetic FileCreatedEvent objects for files under `root`.

    The set of events emitted depends on the state of the tree represented by `root` at the time
    of subscription by an observer. This is useful for replaying file creation events emitted
    by the kernel (a hot observable) by assuming a file's presence under `root` means it was
    created at some point before any downstream observers started listening.
    """

    def subscribe(
        observer: ObserverBase[FileCreatedEvent], scheduler: SchedulerBase | None = None
    ) -> DisposableBase:
        _scheduler = scheduler or CurrentThreadScheduler.singleton()
        disposable = Disposable()

        def walk(*__: Any) -> None:
            nonlocal disposable

            try:
                if not root.is_dir() or disposable.is_disposed:
                    # either the target directory does not exist yet (meaning there
                    # are not events to replay) or the stream has been disposed of
                    return

                for top, _, files in os.walk(root):
                    if disposable.is_disposed:
                        # Ignore: Mypy unreachable
                        # Reason: This code is reachable because disposable is thread-safe
                        #  and the scheduler could run this action on any thread. This
                        #  double-check has to happen since another thread could dispose this
                        #  stream in between checks
                        return  # type: ignore[unreachable]

                    for file in files:
                        if disposable.is_disposed:
                            # Ignore: Mypy unreachable
                            # Reason: This code is reachable because disposable is thread-safe
                            #  and the scheduler could run this action on any thread. This
                            #  double-check has to happen since another thread could dispose this
                            #  stream in between checks
                            return  # type: ignore[unreachable]

                        path = Path(top, file)
                        event = FileCreatedEvent(src_path=str(path), is_synthetic=True)
                        observer.on_next(event)

                observer.on_completed()
            except Exception as e:
                observer.on_error(e)

            return

        return CompositeDisposable(_scheduler.schedule(walk), disposable)

    return rx.create(subscribe)
