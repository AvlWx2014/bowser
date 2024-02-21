import logging

from ...extensions.rx import ObservableTransformer
from ...inotify import InotifyEventData

LOGGER = logging.getLogger("bowser")


class WatchStrategy(ObservableTransformer[InotifyEventData]):
    pass
