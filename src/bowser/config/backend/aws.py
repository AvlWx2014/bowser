from typing import Literal

from pydantic import BaseModel, SecretStr

from ...extensions import Literally
from .base import BowserBackendConfig


class Bucket(BaseModel, frozen=True):
    name: str
    """The target bucket name."""
    key: str = ""
    """The root key content should go under.

    If, for example, this is empty then content will be sync'd directly to the top-level
    of the given bucket name.

    If it is not empty, then content will be sync'd under the provided key.
    """


class AwsBowserBackendConfig(BowserBackendConfig, frozen=True):
    region: str
    """AWS Region."""
    access_key_id: SecretStr
    """AWS Access Key ID."""
    secret_access_key: SecretStr
    """AWS Secret Access Key."""


class AwsS3BowserBackendConfig(AwsBowserBackendConfig, frozen=True):
    buckets: list[Bucket]
    """The target buckets to synchronize content to."""
    kind: Literal["AWS-S3"] = Literally("AWS-S3")
