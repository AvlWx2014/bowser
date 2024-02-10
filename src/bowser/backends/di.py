from collections.abc import Collection, MutableSequence
from functools import cache
from typing import TYPE_CHECKING

from boto3 import Session as Boto3Session

from ..config.backend.aws import AwsS3BowserBackendConfig
from ..config.base import BowserConfig
from .aws import AwsS3Backend
from .base import BowserBackend

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def provide_BowserBackend(  # noqa: N802
    config: BowserConfig,
) -> Collection[BowserBackend]:
    backends: MutableSequence[BowserBackend] = []
    for backend_config in config.backends:
        match backend_config:
            case AwsS3BowserBackendConfig():
                client = provide_S3Client(provide_boto3_Session(), backend_config)
                backends.append(AwsS3Backend(backend_config, client=client))
            case _:
                raise RuntimeError(
                    "Exhaustive match on backend config type failed to match."
                    f"Unknown config type {type(backend_config)}"
                )
    return backends


@cache
def provide_boto3_Session() -> Boto3Session:  # noqa: N802
    return Boto3Session()


def provide_S3Client(  # noqa: N802
    session: Boto3Session, config: AwsS3BowserBackendConfig
) -> "S3Client":
    return session.client(
        "s3",
        region_name=config.region,
        aws_access_key_id=config.access_key_id.get_secret_value(),
        aws_secret_access_key=config.secret_access_key.get_secret_value(),
        use_ssl=True,
        verify=True,
    )
