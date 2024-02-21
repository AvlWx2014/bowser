from enum import Enum
from pathlib import Path

from attr import frozen


class InotifyEvent(Enum):
    """Enumeration of event names from inotifywait(1).

    ISDIR and UNKNOWN are not present in the man page list on linux.die.net. ISDIR was observed
    in practice, and added here to reflect that. UNKNOWN has been added as a fallback option
    in the event that an event is encountered in the wild that is not reflected in the manpage.

    The docstrings for all except ISDIR and UNKNOWN have been taken directly from the manpage
    description of each event.

    See Also:
        The man page for inotifywait(1): https://linux.die.net/man/1/inotifywait
    """

    ACCESS = "ACCESS"
    """A watched file or a file within a watched directory was read from."""
    ATTRIB = "ATTRIB"
    """The metadata of a watched file or a file within a watched directory was modified.

    This includes timestamps, file permissions, extended attributes etc.
    """
    CLOSE_NOWRITE = "CLOSE_NOWRITE"
    """
    A watched file or a file in a watched directory was closed after being opened in read-only mode.
    """
    CLOSE_WRITE = "CLOSE_WRITE"
    """
    A watched file or a file in a watched directory was closed after being opened in writable mode.

    This does not necessarily imply the file was written to.
    """
    CLOSE = "CLOSE"
    """A watched file or a file in a watched directory was closed regardless of how it was opened.

    Note that this is actually implemented simply by listening for both close_write and
    close_nowrite, hence all close events received will be output as one of these, not CLOSE.

    Note:
        From the author of this module: though the manpage description asserts that "all close
        events will be output as one of [close_write or close_nowrite], not CLOSE" the
        event name CLOSE has been observed in practice as of inotify-tools-3.22.1.0-5.fc39.x86_64.
    """
    CREATE = "CREATE"
    """A file or directory was created within a watched directory."""
    DELETE = "DELETE"
    """A file or directory within a watched directory was deleted."""
    DELETE_SELF = "DELETE_SELF"
    """A watched file or directory was deleted.

    After this event the file or directory is no longer being watched. Note that this event can
    occur even if it is not explicitly being listened for.
    """
    ISDIR = "ISDIR"
    """The subject of the event in question is a directory."""
    OPEN = "OPEN"
    """A watched file or a file within a watched directory was opened."""
    MODIFY = "MODIFY"
    """A watched file or a file within a watched directory was written to."""
    MOVED_TO = "MOVED_TO"
    """A file or directory was moved into a watched directory.

    This event occurs even if the file is simply moved from and to the same directory.
    """
    MOVED_FROM = "MOVED_FROM"
    """A file or directory was moved from a watched directory.

    This event occurs even if the file is simply moved from and to the same directory.
    """
    MOVE_SELF = "MOVE_SELF"
    """A watched file or directory was moved.

    After this event, the file or directory is no longer being watched.
    """
    UNMOUNT = "UNMOUNT"
    """The filesystem on which a watched file or directory resides was unmounted.

    After this event the file or directory is no longer being watched. Note that this event can
    occur even if it is not explicitly being listened to.
    """
    UNKNOWN = "UNKNOWN"
    """A fallback for any undocumented events that might arise."""


@frozen
class InotifyEventData:
    watch: Path
    """The watched file or directory."""
    events: set[InotifyEvent]
    """A set of events that occurred."""
    subject: str = ""
    """The file or directory which caused an event to occur."""
