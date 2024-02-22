import logging
import shlex
import subprocess
from abc import ABC, abstractmethod
from typing import Any, BinaryIO, Generic, TypeVar, cast

from reactivex import Observable
from reactivex.abc import DisposableBase, ObserverBase, SchedulerBase
from reactivex.disposable import CompositeDisposable, Disposable
from reactivex.scheduler import CurrentThreadScheduler

LOGGER = logging.getLogger("bowser")


_T_out = TypeVar("_T_out", covariant=True)


class ObservableTransformer(ABC, Generic[_T_out]):
    @abstractmethod
    def __call__(self, upstream: Observable[_T_out]) -> Observable[_T_out]:
        raise NotImplementedError()


def observable_background_process(
    command: str, scheduler: SchedulerBase | None = None
) -> Observable[bytes]:
    """Creates a cold Observable of lines from stdout of a background process.

    This function assumes the process is a background or daemon process that is meant to run
    indefinitely.

    The implementation is taken heavily from the implementation of the factory
    :func:`reactivex.observable.from_iterable`.

    See Also:
        https://github.com/ReactiveX/RxPY/blob/master/reactivex/observable/fromiterable.py
    """

    def subscribe(
        observer: ObserverBase[bytes], scheduler_: SchedulerBase | None
    ) -> DisposableBase:
        # Prefer schedulers in this order:
        # 1. the one passed to the observable factory function
        # 2. the one passed to this subscribe function by the reactivex subscribe internals
        # 3. a scheduler representing the current thread of execution
        # In practice (2) never seems to be fulfilled, even when a call to
        # `reactivex.operators.subscribe_on` is present in the chain, which is curious since this
        # is exactly where I'd expect to see a call to `subscribe_on` manifest.
        _scheduler = scheduler or scheduler_ or CurrentThreadScheduler.singleton()
        disposed = False

        def dispose() -> None:
            nonlocal disposed
            disposed = True

        def action(_: SchedulerBase, __: Any | None) -> None:
            nonlocal disposed
            proc = subprocess.Popen(  # nosec B603
                shlex.split(command),
                shell=False,
                stdout=subprocess.PIPE,
            )
            stdout = cast(BinaryIO, proc.stdout)
            LOGGER.debug("Starting Observable flow from process %d", proc.pid)
            try:
                while not disposed:
                    # readline blocks until there is output on stdout
                    line = stdout.readline().strip()
                    if line:
                        observer.on_next(line)
                observer.on_completed()
            except Exception as e:
                observer.on_error(e)
            finally:
                LOGGER.debug(
                    "Terminal event on Observable. Killing underlying process %d",
                    proc.pid,
                )
                proc.kill()

        disposable = Disposable(dispose)
        return CompositeDisposable(_scheduler.schedule(action), disposable)

    return Observable(subscribe)
