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
        secret_access_key="testing",
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
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
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
        yield boto3.client("s3")


@pytest.fixture
def s3_with_buckets(fake_s3_client, fake_configuration: AwsS3BowserBackendConfig):
    for bucket in fake_configuration.buckets:
        fake_s3_client.create_bucket(Bucket=bucket.name)


@pytest.fixture
def fake_workspace(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "subtree").mkdir()
    for file in (
        Path("evidence.txt"),
        Path("subtree/evidence.json"),
        Path("subtree/evidence.metadata"),
        Path(".bowser.ready"),
    ):
        workspace.joinpath(file).touch()
    return workspace


def test_aws_bowser_backend(
    s3_with_buckets,
    fake_s3_client,
    fake_configuration: AwsS3BowserBackendConfig,
    fake_workspace: Path,
):
    backend = AwsS3Backend(config=fake_configuration, client=fake_s3_client)
    backend.upload(fake_workspace)
    for bucket in fake_configuration.buckets:
        expected_keys = {
            # .metadata and .bowser.{ready,complete} files should be skipped
            f"{bucket.key}/workspace/evidence.txt",
            f"{bucket.key}/workspace/subtree/evidence.json",
        }
        objects = fake_s3_client.list_objects(Bucket=bucket.name)["Contents"]
        for object in objects:
            key = object["Key"]
            assert_that(expected_keys, has_item(key))
