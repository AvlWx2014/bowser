import logging
from abc import ABC
from pathlib import Path

import reactivex.operators as ops
from reactivex import Observable
from reactivex.abc import DisposableBase, ObserverBase, SchedulerBase
from watchdog.events import FileCreatedEvent

from ...extensions.rx import ObservableTransformer

LOGGER = logging.getLogger("bowser")


class WatchStrategy(ObservableTransformer[FileCreatedEvent], ABC):
    pass


class CountWatchStrategy(WatchStrategy):
    """Let the first ``n`` CREATE .bowser.ready events pass through before completing."""

    def __init__(self, n: int) -> None:
        self._n = n

    def __call__(
        self, upstream: Observable[FileCreatedEvent]
    ) -> Observable[FileCreatedEvent]:

        def predicate(event: FileCreatedEvent) -> bool:
            src = event.src_path
            if isinstance(src, bytes):
                src = src.decode("utf-8")
            return Path(src).name == ".bowser.ready"

        def subscribe(
            observer: ObserverBase[FileCreatedEvent],
            scheduler: SchedulerBase | None = None,
        ) -> DisposableBase:
            return upstream.pipe(
                ops.filter(predicate),
                ops.take(self._n),
            ).subscribe(
                on_next=observer.on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed,
                scheduler=scheduler,
            )

        return Observable(subscribe)


class SentinelWatchStrategy(WatchStrategy):
    """Let events pass through, completing once a CREATE event for ``sentinel`` is encountered."""

    def __init__(self, watch_root: Path, *, sentinel: str = ".bowser.complete") -> None:
        self._watch_root = watch_root
        self._sentinel = sentinel

    def __call__(
        self, upstream: Observable[FileCreatedEvent]
    ) -> Observable[FileCreatedEvent]:
        def subscribe(
            observer: ObserverBase[FileCreatedEvent],
            scheduler: SchedulerBase | None = None,
        ) -> DisposableBase:

            def on_next(event: FileCreatedEvent) -> None:
                observer.on_next(event)

                src = event.src_path
                if isinstance(src, bytes):
                    src = src.decode("utf-8")

                as_path = Path(src)
                relative = as_path.relative_to(self._watch_root)
                if str(relative) == self._sentinel:
                    observer.on_completed()

            return upstream.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed,
                scheduler=scheduler,
            )

        return Observable(subscribe)
