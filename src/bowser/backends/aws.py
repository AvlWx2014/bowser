import logging
import os
from collections.abc import Mapping, MutableSequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, cast
from urllib.parse import urlencode

from ..result import Result

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3ServiceResource

from ..config.backend.aws import AwsS3BowserBackendConfig, Bucket
from ..config.link import Link
from ._common import get_metadata_for_file
from .base import BowserBackend

LOGGER = logging.getLogger("bowser")

AWS_TAG_MAXIMUM = 10


class _FileMetadataPair(NamedTuple):
    file: Path
    metadata: Mapping[str, str]


class AwsS3Backend(BowserBackend):

    def __init__(
        self,
        watch_root: Path,
        config: AwsS3BowserBackendConfig,
        resource: "S3ServiceResource",
    ):
        super().__init__(watch_root)
        self._config = config
        self._s3 = resource

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(config={self._config!r})"

    def __str__(self) -> str:
        return self.__class__.__name__

    def _filter(self, filename: str) -> bool:
        not_bowser = not filename.startswith(".bowser")
        not_metadata = not filename.endswith(".metadata")
        return not_bowser and not_metadata

    def _clear_prefix(self, bucket: Bucket, prefix: str) -> Result[int]:
        LOGGER.info(
            "Clearing prefix %s...",
            prefix,
        )
        s3bucket = self._s3.Bucket(bucket.name)
        objects = s3bucket.objects.filter(Prefix=prefix)
        try:
            response = objects.delete()
        except Exception as e:
            return Result[int].failure(e)

        deleted = sum(len(obj.get("Deleted", [])) for obj in response)
        return Result[int].success(deleted)

    def clear_prefix(self, bucket: Bucket, prefix: str) -> int:
        result = self._clear_prefix(bucket, prefix)
        if (exc := result.exception_or_none()) is not None:
            raise exc

        return cast(int, result.get_or_none())

    def upload(self, source: Path) -> None:
        """Upload files in the tree rooted at ``source`` to AWS S3.

        The name of ``source`` likewise becomes the root of the resulting object's key
        on S3.
        """
        source_as_relative_path = source.relative_to(self.watch_root)
        for bucket in self._config.buckets:
            source_prefix = bucket / source_as_relative_path
            # clear link
            if bucket.link is not None:
                # first, for each bucket ensure any links are deleted before possibly being
                # re-created
                # assumes that links are somewhere on the path between the watch root and the tree
                # rooted at `source`, which is the parent for all objects being uploaded
                if bucket.link.target.matches(source_prefix):
                    link_prefix = bucket.link.substitute(source_prefix)
                    deleted = self.clear_prefix(bucket, link_prefix)
                    LOGGER.info(
                        "Removed %d objects from link prefix %s...",
                        deleted,
                        link_prefix,
                    )

            s3bucket = self._s3.Bucket(bucket.name)

            # clear destination to make upload idempotent on retries
            deleted = self.clear_prefix(bucket, source_prefix)
            LOGGER.info(
                "Removed %d objects from prefix %s...",
                deleted,
                source_prefix,
            )

            # resovle files for upload
            for_upload: MutableSequence[_FileMetadataPair] = []
            for root, _, files in os.walk(source):
                for file in filter(self._filter, files):
                    local = Path(root, file)
                    metadata: Mapping[str, Any] = get_metadata_for_file(local)
                    for_upload.append(_FileMetadataPair(local, metadata))

            for path, meta in for_upload:
                as_relative_path = path.relative_to(self.watch_root)
                key = bucket / as_relative_path
                tags = _convert_metadata_to_s3_object_tags(meta)
                LOGGER.info("Uploading %s to %s/%s", path, bucket.name, key)
                s3bucket.upload_file(
                    Filename=str(path),
                    Key=key,
                    ExtraArgs={"Tagging": tags, "ChecksumAlgorithm": "SHA256"},
                )
                if bucket.link is not None and bucket.link.target.matches(key):
                    link_key = bucket.link.substitute(key)
                    LOGGER.info("Uploading %s to %s/%s", path, bucket.name, link_key)
                    s3bucket.upload_file(
                        Filename=str(path),
                        Key=link_key,
                        ExtraArgs={"Tagging": tags, "ChecksumAlgorithm": "SHA256"},
                    )
                LOGGER.info("Done.")


def _convert_metadata_to_s3_object_tags(
    metadata: Mapping[str, Any], limit: int = AWS_TAG_MAXIMUM
) -> str:
    limit = max(limit, 1)
    pairs = tuple(metadata.items())
    stringified = tuple((_, str(v)) for _, v in pairs)
    return urlencode(stringified[:limit])
