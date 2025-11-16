import logging
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import boto3
import pytest
from collektions import first
from moto import mock_aws
from mypy_boto3_s3.service_resource import S3ServiceResource
from pydantic import SecretStr

from bowser.backends.aws import AsyncDispatcher, AwsS3Backend, S3SyncOperation
from bowser.config.backend.aws import AwsS3BowserBackendConfig, Bucket
from bowser.config.link import Link, RegexLinkTargetMatcher
from bowser.deforestation import configure_logging
from bowser.result import Result

HERE = Path(__file__).parent
DATA = HERE / "data"


@pytest.fixture
def fake_configuration():
    return AwsS3BowserBackendConfig(
        region="us-east-1",
        access_key_id="testing",
        secret_access_key="testing",  # nosec B106
        buckets=[Bucket(name="test-bucket", key="i/am/root")],
    )


@pytest.fixture
def fake_aws_credentials(fake_configuration: AwsS3BowserBackendConfig):
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = (
        fake_configuration.access_key_id.get_secret_value()
    )
    os.environ["AWS_SECRET_ACCESS_KEY"] = (
        fake_configuration.secret_access_key.get_secret_value()
    )
    os.environ["AWS_DEFAULT_REGION"] = fake_configuration.region
    # these two aren't used by bowser, but ensure they're mocked out just in case
    # boto would go searching for other credentials in their absence
    os.environ["AWS_SECURITY_TOKEN"] = "testing"  # nosec B105
    os.environ["AWS_SESSION_TOKEN"] = "testing"  # nosec B105
    yield
    for key in (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_DEFAULT_REGION",
        "AWS_SECURITY_TOKEN",
        "AWS_SESSION_TOKEN",
    ):
        del os.environ[key]


@pytest.fixture
def fake_s3_client(fake_aws_credentials):
    with mock_aws():
        yield boto3.resource("s3")


@pytest.fixture
def s3_with_buckets(fake_s3_client, fake_configuration: AwsS3BowserBackendConfig):
    for bucket in fake_configuration.buckets:
        fake_s3_client.create_bucket(Bucket=bucket.name)


@pytest.fixture
def fake_workspace(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    common_root = workspace / Path("common/ancestors")
    common_root.mkdir(parents=True)
    for subpath in (
        Path("app1/content.txt"),
        Path("app1/.bowser.ready"),
        Path("app2/subtree/content.json"),
        Path("app2/subtree/content.metadata"),
        Path("app2/subtree/content.txt"),
        Path("app2/.bowser.ready"),
        Path("app3/report.yml"),
        Path("app3/.bowser.ready"),
    ):
        application_file = common_root / subpath
        application_file.parent.mkdir(parents=True, exist_ok=True)
        application_file.touch()
    return workspace


def test_aws_s3_backend_filters_bowser_and_metadata_files(
    fake_configuration: AwsS3BowserBackendConfig,
    fake_workspace: Path,
) -> None:
    backend = AwsS3Backend(
        watch_root=fake_workspace,
        config=fake_configuration,
        resource=MagicMock(spec=S3ServiceResource),
    )
    expected = set()
    for f in ("app2/subtree/content.json", "app2/subtree/content.txt"):
        expected.add(str(fake_workspace / "common/ancestors" / f))
    tree = fake_workspace / "common/ancestors" / "app2"
    actual = set()
    for root, _, files in os.walk(tree):
        for f in filter(backend._filter, files):
            actual.add(str(Path(root, f)))
    assert actual == expected


def test_aws_s3_backend_index_source(
    fake_configuration: AwsS3BowserBackendConfig,
    fake_workspace: Path,
) -> None:
    backend = AwsS3Backend(
        watch_root=fake_workspace,
        config=fake_configuration,
        resource=MagicMock(spec=S3ServiceResource),
    )
    expected = {
        "common/ancestors/app1/content.txt": fake_workspace
        / "common/ancestors/app1/content.txt",
        "common/ancestors/app2/subtree/content.json": fake_workspace
        / "common/ancestors/app2/subtree/content.json",
        "common/ancestors/app2/subtree/content.txt": fake_workspace
        / "common/ancestors/app2/subtree/content.txt",
        "common/ancestors/app3/report.yml": fake_workspace
        / "common/ancestors/app3/report.yml",
    }
    actual = backend._index_source(fake_workspace)
    assert actual.is_success
    assert actual.get() == expected


def test_aws_s3_backend_op_resolution(
    fake_configuration: AwsS3BowserBackendConfig,
    fake_workspace: Path,
) -> None:
    config = AwsS3BowserBackendConfig(
        region="us-east-1",
        access_key_id=SecretStr("nothing to see here"),
        secret_access_key=SecretStr("nothing to see here"),
        buckets=[
            Bucket(
                name="test-bucket",
                prefix="i/am/root",
                link=Link(name="latest", target=RegexLinkTargetMatcher(pattern="app2")),
            )
        ],
    )
    backend = AwsS3Backend(
        watch_root=fake_workspace,
        config=config,
        resource=MagicMock(spec=S3ServiceResource),
    )
    with patch.object(backend, "_index_destination") as mock_index_destination:
        mock_index_destination.side_effect = [
            Result.success(
                {
                    "i/am/root/common/ancestors/app2/subtree/content.txt",
                    "i/am/root/common/ancestors/app2/subtree/content.yaml",
                }
            ),
            Result.success(
                {
                    "i/am/root/common/ancestors/latest/subtree/content.txt",
                    "i/am/root/common/ancestors/latest/subtree/content.yaml",
                }
            ),
        ]
        expected = {
            S3SyncOperation.Create(
                key="i/am/root/common/ancestors/app2/subtree/content.json",
                source=fake_workspace / "common/ancestors/app2/subtree/content.json",
            ),
            S3SyncOperation.Update(
                key="i/am/root/common/ancestors/app2/subtree/content.txt",
                source=fake_workspace / "common/ancestors/app2/subtree/content.txt",
            ),
            S3SyncOperation.Delete(
                key="i/am/root/common/ancestors/app2/subtree/content.yaml"
            ),
            S3SyncOperation.Create(
                key="i/am/root/common/ancestors/latest/subtree/content.json",
                source=fake_workspace / "common/ancestors/app2/subtree/content.json",
            ),
            S3SyncOperation.Update(
                key="i/am/root/common/ancestors/latest/subtree/content.txt",
                source=fake_workspace / "common/ancestors/app2/subtree/content.txt",
            ),
            S3SyncOperation.Delete(
                key="i/am/root/common/ancestors/latest/subtree/content.yaml"
            ),
        }

        source = fake_workspace / "common/ancestors/app2"
        actual = set(
            backend._resolve(
                source,
                first(config.buckets),
                prefix="common/ancestors/app2",
            )
        )
        assert actual == expected


def test_aws_s3_backend_upload_dry_run(
    caplog: pytest.LogCaptureFixture,
    fake_configuration: AwsS3BowserBackendConfig,
    fake_workspace: Path,
) -> None:
    config = AwsS3BowserBackendConfig(
        region="us-east-1",
        access_key_id=SecretStr("nothing to see here"),
        secret_access_key=SecretStr("nothing to see here"),
        buckets=[
            Bucket(
                name="test-bucket",
                prefix="i/am/root",
                link=Link(name="latest", target=RegexLinkTargetMatcher(pattern="app2")),
            )
        ],
    )
    backend = AwsS3Backend(
        watch_root=fake_workspace,
        config=config,
        resource=MagicMock(spec=S3ServiceResource),
    )
    tree = fake_workspace / "common/ancestors/app2"
    with (
        patch.object(backend, "_index_destination") as mock_index_destination,
        caplog.at_level(logging.INFO),
    ):
        configure_logging(debug=False)
        mock_index_destination.side_effect = [
            Result.success(
                {
                    "i/am/root/common/ancestors/app2/subtree/content.txt",
                    "i/am/root/common/ancestors/app2/subtree/content.yaml",
                }
            ),
            Result.success(
                {
                    "i/am/root/common/ancestors/latest/subtree/content.txt",
                    "i/am/root/common/ancestors/latest/subtree/content.yaml",
                }
            ),
        ]
        backend.upload_dry_run(tree)
        expected = {
            f"Would Create i/am/root/common/ancestors/app2/subtree/content.json from {fake_workspace / 'common/ancestors/app2/subtree/content.json'}",
            f"Would Update i/am/root/common/ancestors/app2/subtree/content.txt from {fake_workspace / 'common/ancestors/app2/subtree/content.txt'}",
            "Would Delete i/am/root/common/ancestors/app2/subtree/content.yaml",
            f"Would Create i/am/root/common/ancestors/latest/subtree/content.json from {fake_workspace / 'common/ancestors/app2/subtree/content.json'}",
            f"Would Update i/am/root/common/ancestors/latest/subtree/content.txt from {fake_workspace / 'common/ancestors/app2/subtree/content.txt'}",
            "Would Delete i/am/root/common/ancestors/latest/subtree/content.yaml",
        }
        actual = {record.getMessage() for record in caplog.records}
        assert (actual & expected) == expected


def test_aws_s3_backend_upload(
    fake_configuration: AwsS3BowserBackendConfig,
    fake_workspace: Path,
) -> None:
    config = AwsS3BowserBackendConfig(
        region="us-east-1",
        access_key_id=SecretStr("nothing to see here"),
        secret_access_key=SecretStr("nothing to see here"),
        buckets=[
            Bucket(
                name="test-bucket",
                prefix="i/am/root",
                link=Link(name="latest", target=RegexLinkTargetMatcher(pattern="app2")),
            )
        ],
    )
    backend = AwsS3Backend(
        watch_root=fake_workspace,
        config=config,
        resource=MagicMock(spec=S3ServiceResource),
    )
    tree = fake_workspace / "common/ancestors/app2"

    with (
        patch.object(backend, "_index_destination") as mock_index_destination,
        patch("bowser.backends.aws.AsyncDispatcher") as mock_dispatcher,
    ):
        dispatcher = MagicMock(spec=AsyncDispatcher)
        dispatcher.dispatch.return_value = {
            S3SyncOperation.Create: 2,
            S3SyncOperation.Update: 2,
            S3SyncOperation.Delete: 2,
        }
        dispatcher.__enter__.return_value = dispatcher
        dispatcher.__exit__.return_value = None
        mock_dispatcher.return_value = dispatcher

        mock_index_destination.side_effect = [
            Result.success(
                {
                    "i/am/root/common/ancestors/app2/subtree/content.txt",
                    "i/am/root/common/ancestors/app2/subtree/content.yaml",
                }
            ),
            Result.success(
                {
                    "i/am/root/common/ancestors/latest/subtree/content.txt",
                    "i/am/root/common/ancestors/latest/subtree/content.yaml",
                }
            ),
        ]
        backend.upload(tree)
        dispatcher.dispatch.assert_called_once()
