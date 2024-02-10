from pathlib import Path

from ..config.backend.aws import AwsS3BowserBackendConfig
from .base import BowserBackend


class AwsS3Backend(BowserBackend):

    def __init__(self, config: AwsS3BowserBackendConfig):
        self._config = config

    def sync(self, source: Path) -> None:
        pass
