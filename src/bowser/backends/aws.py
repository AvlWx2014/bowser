import asyncio
import logging
import os
from asyncio import AbstractEventLoop
from collections import Counter
from collections.abc import Collection, Mapping, MutableMapping
from pathlib import Path
from typing import Any, Self
from urllib.parse import urlencode

import aioboto3
from attrs import field, frozen
from collektions import map_keys
from mypy_boto3_s3.service_resource import S3ServiceResource
from types_aiobotocore_s3.service_resource import (
    S3ServiceResource as AsyncS3ServiceResource,
)

from ..config.backend.aws import AwsS3BowserBackendConfig, Bucket
from ..result import Result
from ._common import get_metadata_for_file
from .base import BowserBackend

LOGGER = logging.getLogger("bowser")

AWS_TAG_MAXIMUM = 10


class S3SyncOperation:
    @frozen(kw_only=True)
    class Create:
        key: str
        source: Path
        metadata: Mapping[str, Any] = field(factory=dict, hash=False, eq=False)

    @frozen(kw_only=True)
    class Update:
        key: str
        source: Path
        metadata: Mapping[str, Any] = field(factory=dict, hash=False, eq=False)

    @frozen(kw_only=True)
    class Delete:
        key: str


S3Operation = S3SyncOperation.Create | S3SyncOperation.Update | S3SyncOperation.Delete
S3OperationKind = (
    type[S3SyncOperation.Create]
    | type[S3SyncOperation.Update]
    | type[S3SyncOperation.Delete]
)


class AsyncDispatcher:
    def __init__(
        self, config: AwsS3BowserBackendConfig, loop: AbstractEventLoop | None = None
    ) -> None:
        self._config: AwsS3BowserBackendConfig = config
        self._loop = loop or asyncio.new_event_loop()
        self._owned = loop is None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        if self._owned and not self._loop.is_closed():
            self._loop.close()

    def dispatch(
        self, ops: Collection[S3Operation], bucket: Bucket
    ) -> Counter[S3OperationKind]:
        return self._loop.run_until_complete(self._dispatch(ops, bucket)).get()

    async def _dispatch(
        self, ops: Collection[S3Operation], bucket: Bucket
    ) -> Result[Counter[S3OperationKind]]:
        counter = Counter[S3OperationKind]()
        session = aioboto3.Session()
        async with session.resource(
            "s3",
            aws_access_key_id=self._config.access_key_id.get_secret_value(),
            aws_secret_access_key=self._config.secret_access_key.get_secret_value(),
            region_name=self._config.region,
            use_ssl=True,
            verify=True,
        ) as s3:
            op_types = []
            tasks = []
            for op in ops:
                match op:
                    case S3SyncOperation.Create(
                        key=key, source=source, metadata=metadata
                    ) | S3SyncOperation.Update(
                        key=key, source=source, metadata=metadata
                    ):
                        LOGGER.info("%s %s from %s", op.__class__.__name__, key, source)
                        tasks.append(self.put_object(s3, bucket, key, source, metadata))
                    case S3SyncOperation.Delete(key=key):
                        LOGGER.info("Delete %s", key)
                        tasks.append(self.delete_object(s3, bucket, key))
                op_types.append(type(op))

            results = await asyncio.gather(*tasks)
            # according to the docs, asyncio.gather returns the results
            # in the same order as the original sequence of tasks even though
            # tasks can be executed in any order
            for result, op_t in zip(results, op_types, strict=True):
                if result.is_failure:
                    return Result[Counter[S3OperationKind]].failure(result.exception())
                counter[op_t] += 1

        return Result.success(counter)

    async def put_object(
        self,
        s3: AsyncS3ServiceResource,
        bucket: Bucket,
        key: str,
        source: Path,
        metadata: Mapping[str, str],
    ) -> Result[str]:
        s3bucket = await s3.Bucket(bucket.name)
        tags = _convert_metadata_to_s3_object_tags(metadata)
        try:
            await s3bucket.upload_file(
                Filename=str(source),
                Key=key,
                ExtraArgs={"Tagging": tags, "ChecksumAlgorithm": "SHA256"},
            )
        except Exception as e:
            return Result.failure(e)
        return Result.success(key)

    async def delete_object(
        self, s3: AsyncS3ServiceResource, bucket: Bucket, key: str
    ) -> Result[str]:
        try:
            obj = await s3.Object(bucket.name, key)
            await obj.delete()
        except Exception as e:
            return Result.failure(e)
        return Result.success(key)


class AwsS3Backend(BowserBackend):

    def __init__(
        self,
        watch_root: Path,
        config: AwsS3BowserBackendConfig,
        resource: S3ServiceResource,
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

    def upload(self, source: Path) -> None:
        """Upload files in the tree rooted at ``source`` to AWS S3.

        The name of ``source`` likewise becomes the root of the resulting object's key
        on S3.
        """
        for bucket in self._config.buckets:
            LOGGER.info("Syncing with %s", bucket.name)
            self._sync(source, bucket)
        LOGGER.info("Done.")

    def upload_dry_run(self, source: Path) -> None:
        """
        Only indicate what would be done to upload files in the tree rooted at `source` to AWS S3.
        """
        for bucket in self._config.buckets:
            LOGGER.info("Syncing with %s", bucket.name)
            self._sync_dry_run(source, bucket)
        LOGGER.info("Done.")

    def _sync(self, source: Path, bucket: Bucket) -> None:
        prefix = str(source.relative_to(self.watch_root))
        ops = self._resolve(source, bucket, prefix)
        with AsyncDispatcher(self._config) as dispatcher:
            LOGGER.info("Syncing with %s/%s", bucket.name, prefix)
            try:
                results = dispatcher.dispatch(ops, bucket)
            except Exception:
                LOGGER.exception("Failed to sync with %s/%s", bucket.name, prefix)
                return
        for op_t, completed in results.items():
            LOGGER.info("%s: %d", op_t.__name__, completed)
        total = sum(results.values())
        LOGGER.info("Completed: %d/%d", total, len(ops))

    def _sync_dry_run(self, source: Path, bucket: Bucket) -> None:
        prefix = str(source.relative_to(self.watch_root))
        ops = self._resolve(source, bucket, prefix)
        LOGGER.info("Syncing with %s/%s", bucket.name, prefix)
        results = Counter[S3OperationKind]()
        for op in ops:
            match op:
                case S3SyncOperation.Create(key=key, source=src):
                    LOGGER.info("Would Create %s from %s", key, src)
                case S3SyncOperation.Update(key=key, source=src):
                    LOGGER.info("Would Update %s from %s", key, src)
                case S3SyncOperation.Delete(key=key):
                    LOGGER.info("Would Delete %s", key)
            results[type(op)] += 1

        for op_t, would in results.items():
            LOGGER.info("%s: %d", op_t.__name__, would)
        total = sum(results.values())
        LOGGER.info("Completed: %d/%d", total, len(ops))

    def _resolve(
        self, source: Path, bucket: Bucket, prefix: str
    ) -> Collection[S3Operation]:
        left = self._index_source(source).get()
        left = map_keys(left, lambda k, _: bucket / k)
        prefix = bucket / prefix
        right = self._index_destination(bucket, prefix).get()
        ops = list(_into_ops(left, right))
        if (link := bucket.link) is not None and link.target.matches(prefix):
            link_prefix = link.substitute(prefix)
            left = map_keys(left, lambda k, _: link.substitute(k))
            right = self._index_destination(bucket, link_prefix).get()
            ops.extend(_into_ops(left, right))
        return ops

    def _index_source(self, source: Path) -> Result[Mapping[str, Path]]:
        idx: MutableMapping[str, Path] = {}
        for root, _, files in os.walk(str(source)):
            for file in filter(self._filter, files):
                as_path = Path(root, file)
                as_key = str(as_path.relative_to(self.watch_root))
                idx[as_key] = as_path
        return Result.success(idx)

    def _index_destination(self, destination: Bucket, prefix: str) -> Result[set[str]]:
        idx = set()
        s3bucket = self._s3.Bucket(destination.name)
        for obj in s3bucket.objects.filter(Prefix=prefix):
            idx.add(obj.key)
        return Result.success(idx)


def _into_ops(left: Mapping[str, Path], right: set[str]) -> Collection[S3Operation]:
    ops: list[S3Operation] = []

    for to_create in left.keys() - right:
        path = left[to_create]
        metadata = get_metadata_for_file(path)
        ops.append(
            S3SyncOperation.Create(key=to_create, source=path, metadata=metadata)
        )

    for to_update in left.keys() & right:
        path = left[to_update]
        metadata = get_metadata_for_file(path)
        ops.append(
            S3SyncOperation.Update(key=to_update, source=path, metadata=metadata)
        )

    for to_delete in right - left.keys():
        ops.append(S3SyncOperation.Delete(key=to_delete))

    return ops


def _convert_metadata_to_s3_object_tags(
    metadata: Mapping[str, Any], limit: int = AWS_TAG_MAXIMUM
) -> str:
    limit = max(limit, 1)
    pairs = tuple(metadata.items())
    stringified = tuple((_, str(v)) for _, v in pairs)
    return urlencode(stringified[:limit])
