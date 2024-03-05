from collections.abc import Collection, Generator, Iterator, MutableSequence
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import boto3
from moto import mock_aws

from ..config.backend.aws import AwsS3BowserBackendConfig
from ..config.base import BowserConfig
from .aws import AwsS3Backend
from .base import BowserBackend

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

_CLOSE_T = Literal["close"]
_CLOSE: _CLOSE_T = "close"


@contextmanager
def provide_BowserBackends(  # noqa: N802
    watch_root: Path, config: BowserConfig, dry_run: bool  # noqa: FBT001
) -> Iterator[Collection[BowserBackend]]:
    backends: MutableSequence[BowserBackend] = []
    closeables: MutableSequence[Generator[Any, _CLOSE_T, None]] = []
    for backend_config in config.backends:
        match backend_config:
            case AwsS3BowserBackendConfig():
                provider = provide_S3Client(backend_config, dry_run)
                backends.append(
                    AwsS3Backend(
                        watch_root=watch_root,
                        config=backend_config,
                        client=next(provider),
                    )
                )
                closeables.append(provider)
            case _:
                raise RuntimeError(
                    "Exhaustive match on backend config type failed to match."
                    f"Unknown config type {type(backend_config)}"
                )
    yield backends
    for closeable in closeables:
        with suppress(StopIteration):
            closeable.send(_CLOSE)


def provide_S3Client(  # noqa: N802
    config: AwsS3BowserBackendConfig, dry_run: bool  # noqa: FBT001
) -> Generator["S3Client", _CLOSE_T, None]:
    kwargs = {
        "region_name": config.region,
        "aws_access_key_id": config.access_key_id.get_secret_value(),
        "aws_secret_access_key": config.secret_access_key.get_secret_value(),
        "use_ssl": True,
        "verify": True,
    }
    if dry_run:
        with mock_aws():
            client = boto3.client("s3", **kwargs)  # type: ignore[call-overload]
            for bucket in config.buckets:
                location = {"LocationConstraint": config.region}
                client.create_bucket(
                    Bucket=bucket.name, CreateBucketConfiguration=location
                )
    else:
        client = boto3.client("s3", **kwargs)  # type: ignore[call-overload]

    signal = yield client
    if signal == _CLOSE:
        client.close()
