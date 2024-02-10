from pathlib import Path

from ..config.backend.aws import AwsS3BowserBackendConfig
from .base import BowserBackend


class AwsS3Backend(BowserBackend):

    def __init__(self, config: AwsS3BowserBackendConfig):
        self._config = config

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(config={self._config!r})"

    def __str__(self) -> str:
        return self.__class__.__name__

    def upload(self, source: Path) -> None:
        pass
