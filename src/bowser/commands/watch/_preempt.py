import logging
from pathlib import Path

from reactivex import Observable
from reactivex.abc import DisposableBase, ObserverBase, SchedulerBase
from watchdog.events import FileCreatedEvent

from bowser.extensions.rx import ObservableTransformer

LOGGER = logging.getLogger("bowser")


class PreemptObservable(ObservableTransformer[FileCreatedEvent]):
    def __init__(self, sentinel: Path | None = None) -> None:
        self._sentinel = sentinel or Path(".bowser.abort")

    def __call__(
        self, upstream: Observable[FileCreatedEvent]
    ) -> Observable[FileCreatedEvent]:
        def subscribe(
            observer: ObserverBase[FileCreatedEvent],
            scheduler: SchedulerBase | None = None,
        ) -> DisposableBase:

            def on_next(event: FileCreatedEvent) -> None:
                src = event.src_path
                if isinstance(src, bytes):
                    src = src.decode("utf-8")
                as_path = Path(src)
                if as_path == self._sentinel:
                    LOGGER.info("Abort signal detected")
                    observer.on_completed()
                else:
                    observer.on_next(event)

            return upstream.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed,
                scheduler=scheduler,
            )

        return Observable(subscribe)
