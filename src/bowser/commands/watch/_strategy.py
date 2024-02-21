import logging
from abc import ABC
from pathlib import Path

import reactivex.operators as ops
from reactivex import Observable
from reactivex.abc import DisposableBase, ObserverBase, SchedulerBase

from ...extensions.rx import ObservableTransformer
from ...inotify import InotifyEvent, InotifyEventData

LOGGER = logging.getLogger("bowser")


class WatchStrategy(ObservableTransformer[InotifyEventData], ABC):
    pass


class CountWatchStrategy(WatchStrategy):
    """Let the first ``n`` CREATE .bowser.ready events pass through before completing."""

    def __init__(self, n: int) -> None:
        self._n = n

    def __call__(
        self, upstream: Observable[InotifyEventData]
    ) -> Observable[InotifyEventData]:
        def predicate(event: InotifyEventData) -> bool:
            return (
                InotifyEvent.CREATE in event.events and event.subject == ".bowser.ready"
            )

        return upstream.pipe(
            ops.filter(predicate),
            ops.take(self._n),
        )


class SentinelWatchStrategy(WatchStrategy):
    """Let events pass through, completing once a CREATE event for ``sentinel`` is encountered."""

    def __init__(self, watch_root: Path, *, sentinel: str = ".bowser.complete") -> None:
        self._watch_root = watch_root
        self._sentinel = sentinel

    def __call__(
        self, upstream: Observable[InotifyEventData]
    ) -> Observable[InotifyEventData]:
        def subscribe(
            observer: ObserverBase[InotifyEventData],
            scheduler: SchedulerBase | None = None,
        ) -> DisposableBase:

            def on_next(value: InotifyEventData) -> None:
                observer.on_next(value)
                if (
                    InotifyEvent.CREATE in value.events
                    and self._watch_root == value.watch
                    and self._sentinel == value.subject
                ):
                    observer.on_completed()

            return upstream.subscribe(
                on_next, observer.on_error, observer.on_completed, scheduler=scheduler
            )

        return Observable(subscribe)
