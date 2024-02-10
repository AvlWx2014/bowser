from collections.abc import Collection, MutableSequence

from ..config.backend.aws import AwsS3BowserBackendConfig
from ..config.base import BowserConfig
from .aws import AwsS3Backend
from .base import BowserBackend


def provide_BowserBackend(
    config: BowserConfig,
) -> Collection[BowserBackend]:  # noqa: N802
    backends: MutableSequence[BowserBackend] = []
    for backend_config in config.backends:
        match backend_config:
            case AwsS3BowserBackendConfig():
                backends.append(AwsS3Backend(backend_config))
            case _:
                raise RuntimeError(
                    "Exhaustive match on backend config type failed to match."
                    f"Unknown config type {type(backend_config)}"
                )
    return backends
