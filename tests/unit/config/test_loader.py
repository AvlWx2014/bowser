from pathlib import Path

from hamcrest import assert_that, equal_to

from bowser.config.backend.aws import AwsS3BowserBackendConfig, Bucket
from bowser.config.base import BowserConfig
from bowser.config.loader import load_app_configuration

HERE = Path(__file__).parent
DATA = HERE / "data"


def test_load_app_configuration():
    expected = BowserConfig(
        polling_interval=311,
        backends=[
            AwsS3BowserBackendConfig(
                region="eu-west-1",
                access_key_id="access key",
                secret_access_key="secret squirrel stuff",
                buckets=[Bucket(name="bucket", key="some/root/key")],
            )
        ],
    )
    actual = load_app_configuration(check_paths=(DATA,))
    assert_that(actual, equal_to(expected))
