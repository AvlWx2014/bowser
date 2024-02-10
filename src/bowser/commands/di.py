import os
from concurrent.futures import Executor, ThreadPoolExecutor
from functools import cache


@cache
def provide_Executor() -> Executor:  # noqa: N802
    cpus = os.cpu_count() or 1
    workers = max(cpus - 1, 1) * 2
    return ThreadPoolExecutor(max_workers=workers)
