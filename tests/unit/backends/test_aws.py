import os
from pathlib import Path

import boto3
import pytest
from hamcrest import assert_that, has_item
from moto import mock_aws

from bowser.backends.aws import AwsS3Backend
from bowser.config.backend.aws import AwsS3BowserBackendConfig, Bucket

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


def test_aws_bowser_backend(
    s3_with_buckets,
    fake_s3_client,
    fake_configuration: AwsS3BowserBackendConfig,
    fake_workspace: Path,
):
    backend = AwsS3Backend(
        watch_root=fake_workspace, config=fake_configuration, resource=fake_s3_client
    )
    for application_tree in ("app1", "app2", "app3"):
        source = fake_workspace / "common/ancestors" / application_tree
        backend.upload(source)
    for bucket in fake_configuration.buckets:
        expected_keys = {
            # .metadata and .bowser.{ready,complete} files should be skipped
            f"{bucket.key}/common/ancestors/app1/content.txt".lstrip("/"),
            f"{bucket.key}/common/ancestors/app2/subtree/content.json".lstrip("/"),
            f"{bucket.key}/common/ancestors/app2/subtree/content.txt".lstrip("/"),
            f"{bucket.key}/common/ancestors/app3/report.yml".lstrip("/"),
        }
        s3bucket = fake_s3_client.Bucket(bucket.name)
        objects = s3bucket.objects.all()
        for obj in objects:
            assert_that(expected_keys, has_item(obj.key))
