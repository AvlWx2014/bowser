import logging
import shlex
from pathlib import Path

import reactivex.operators as ops
from reactivex import Observable
from reactivex.abc import SchedulerBase

from ..extensions.rx import observable_background_process
from ._event import InotifyEventData
from ._mapper import output_to_event_data

LOGGER = logging.getLogger("bowser")


def observable_inotifywait(
    watch: Path, scheduler: SchedulerBase | None = None
) -> Observable[InotifyEventData]:
    """Start inotifywait with the provided options and return an Observable of the output.

    The output is pushed one line at a time. Each line is decoded from bytes using 'utf-8'.

    Notes:
        * ``inotifywait`` is automatically started with the options ``-rmq``, which means
          "recursive", "monitor" (run indefinitely), and "quiet" respectively. Note that "quiet"
          suppresses other outputs so only events are written to stdout.
    """
    watch_dir_string = shlex.quote(str(watch))
    command = f"inotifywait -rmq {watch_dir_string}"
    return observable_background_process(command, scheduler).pipe(
        ops.map(lambda line: output_to_event_data(line.decode("utf-8"))),
    )
