from reactivex import Subject
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
