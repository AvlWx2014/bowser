from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from bowser.config.backend.base import BowserBackendConfig
from bowser.extensions import Literally


class Bucket(BaseModel):
    model_config: ConfigDict = ConfigDict(frozen=True)
    """Note: this is Pydantic magic to configure your models e.g. make them frozen.

    Using ``frozen=True`` as an instance attribute ensures a ``__hash__` method is
    generated for the model, allowing it to be used in conjunction with things like
    sets, dicts, and functools.cache.
    """
    name: str
    """The target bucket name."""
    key: str = Field(default="")
    """The root key content should go under.

    If, for example, this is empty then content will be sync'd directly to the top-level
    of the given bucket name.

    If it is not empty, then content will be sync'd under the provided key.
    """


class AwsBowserBackendConfig(BowserBackendConfig):
    access_key_id: SecretStr
    """AWS Access Key ID."""
    secret_access_key: SecretStr
    """AWS Secret Access Key."""


class AwsS3BowserBackendConfig(AwsBowserBackendConfig):
    buckets: list[Bucket]
    """The target buckets to synchronize content to."""
    kind: Literal["AWS-S3"] = Literally("AWS-S3")
