from collections.abc import Collection, Generator, MutableSequence
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, Literal

import boto3
from moto import mock_aws
from mypy_boto3_s3 import S3ServiceResource

from ..config.backend.aws import AwsS3BowserBackendConfig
from ..config.base import BowserConfig
from .aws import AwsS3Backend
from .base import BowserBackend

_CLOSE_T = Literal["close"]
_CLOSE: _CLOSE_T = "close"


@contextmanager
def provide_BowserBackends(  # noqa: N802
    watch_root: Path, config: BowserConfig, dry_run: bool  # noqa: FBT001
) -> Generator[Collection[BowserBackend], None, None]:
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
                        resource=next(provider),
                    )
                )
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
) -> Generator[S3ServiceResource, None, None]:
    kwargs = {
        "region_name": config.region,
        "aws_access_key_id": config.access_key_id.get_secret_value(),
        "aws_secret_access_key": config.secret_access_key.get_secret_value(),
        "use_ssl": True,
        "verify": True,
    }

    if dry_run:
        with mock_aws():
            s3 = boto3.resource("s3", **kwargs)  # type: ignore[call-overload]
            for bucket in config.buckets:
                s3bucket = s3.Bucket(bucket.name)
                location = {"LocationConstraint": config.region}
                s3bucket.create(CreateBucketConfiguration=location)
            # this has to remain here, so we remain within the context of moto while the rest
            # of the program executes
            # moving this call outside of this `with` block means mocking by moto stops before
            # we yield the client back to the caller
            yield s3
    else:
        s3 = boto3.resource("s3", **kwargs)  # type: ignore[call-overload]
        yield s3
