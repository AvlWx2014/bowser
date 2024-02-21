import logging
import shlex
import subprocess
from typing import Any

from reactivex import Observable
from reactivex.abc import DisposableBase, ObserverBase, SchedulerBase
from reactivex.disposable import CompositeDisposable, Disposable
from reactivex.scheduler import CurrentThreadScheduler

LOGGER = logging.getLogger("bowser")


def observable_background_process(
    command: str, scheduler: SchedulerBase | None = None
) -> Observable[bytes]:
    """Creates a hot Observable of lines from stdout of a background process.

    This function assumes the process is a background or daemon process that is meant to run
    indefinitely.

    The implementation is taken heavily from the implementation of the factory
    :func:`reactivex.observable.from_iterable`.

    See Also:
        https://github.com/ReactiveX/RxPY/blob/master/reactivex/observable/fromiterable.py
    """

    def subscribe(
        observer: ObserverBase[bytes], scheduler_: SchedulerBase
    ) -> DisposableBase:
        _scheduler = scheduler or scheduler_ or CurrentThreadScheduler.singleton()
        LOGGER.debug("Scheduler in use: %s", _scheduler)
        disposed = False

        def dispose() -> None:
            nonlocal disposed
            LOGGER.debug("Disposing Observable process stream.")
            disposed = True

        def action(_: SchedulerBase, __: Any | None) -> None:
            nonlocal disposed
            proc = subprocess.Popen(
                shlex.split(command),
                stdout=subprocess.PIPE,
            )
            try:
                while not disposed:
                    # readline blocks until there is output on stdout
                    line = proc.stdout.readline().strip()
                    if line:
                        observer.on_next(line)
            except Exception as e:
                observer.on_error(e)
            finally:
                LOGGER.debug("Disposing underlying process %d", proc.pid)
                proc.kill()
                observer.on_completed()

        disposable = Disposable(dispose)
        return CompositeDisposable(_scheduler.schedule(action), disposable)

    return Observable(subscribe)
