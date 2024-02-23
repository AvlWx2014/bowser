import logging
import os
from collections.abc import Mapping, MutableSequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple
from urllib.parse import urlencode

from ..config.backend.aws import AwsS3BowserBackendConfig
from ._common import get_metadata_for_file
from .base import BowserBackend

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


LOGGER = logging.getLogger("bowser")


AWS_TAG_MAXIMUM = 10


class _FileMetadataPair(NamedTuple):
    file: Path
    metadata: Mapping[str, str]


class AwsS3Backend(BowserBackend):

    def __init__(
        self, watch_root: Path, config: AwsS3BowserBackendConfig, client: "S3Client"
    ):
        super().__init__(watch_root)
        self._config = config
        self._client = client

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(config={self._config!r})"

    def __str__(self) -> str:
        return self.__class__.__name__

    def _filter(self, filename: str) -> bool:
        not_bowser = not filename.startswith(".bowser")
        not_metadata = not filename.endswith(".metadata")
        return not_bowser and not_metadata

    def upload(self, source: Path) -> None:
        """Upload files in the tree rooted at ``source`` to AWS S3.

        The name of ``source`` likewise becomes the root of the resulting object's key
        on S3.
        """
        for_upload: MutableSequence[_FileMetadataPair] = []
        for root, _, files in os.walk(source):
            for file in filter(self._filter, files):
                local = Path(root, file)
                metadata: Mapping[str, Any] = get_metadata_for_file(local)
                for_upload.append(_FileMetadataPair(local, metadata))

        for bucket in self._config.buckets:
            for path, meta in for_upload:
                relative_path = path.relative_to(self.watch_root)
                # lstrip to remove any unwanted leading "/" e.g. if `bucket.key` is empty
                key = f"{bucket.key}/{relative_path!s}".lstrip("/")
                tags = _convert_metadata_to_s3_object_tags(meta)
                LOGGER.info("Uploading %s to %s/%s", path, bucket.name, key)
                self._client.put_object(
                    Body=str(path),
                    Bucket=bucket.name,
                    Key=key,
                    Tagging=tags,
                    ChecksumAlgorithm="SHA256",
                )
                LOGGER.info("Done.")


def _convert_metadata_to_s3_object_tags(
    metadata: Mapping[str, Any], limit: int = AWS_TAG_MAXIMUM
) -> str:
    limit = max(limit, 1)
    pairs = tuple(metadata.items())
    stringified = tuple((_, str(v)) for _, v in pairs)
    return urlencode(stringified[:limit])
