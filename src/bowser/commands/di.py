import os
from concurrent.futures import Executor, ThreadPoolExecutor
from functools import cache


@cache
def provide_Executor() -> Executor:  # noqa: N802
    workers = max(os.cpu_count() - 1, 1) * 2
    return ThreadPoolExecutor(max_workers=workers)
