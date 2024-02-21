from pathlib import Path

from bowser.inotify._event import InotifyEvent, InotifyEventData


def output_to_event_data(line: str) -> InotifyEventData:
    watch, event_names, *rest = line.split()
    events = set()
    for event_name in event_names.split(","):
        try:
            event = InotifyEvent[event_name]
        except KeyError:
            event = InotifyEvent.UNKNOWN
        events.add(event)
    kwargs = {"watch": Path(watch), "events": events}
    if rest:
        kwargs["subject"] = rest[0]
    return InotifyEventData(**kwargs)
