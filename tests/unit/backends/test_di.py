from pathlib import Path

from hamcrest import assert_that, contains_inanyorder

from bowser.backends.aws import AwsS3Backend
from bowser.backends.di import provide_BowserBackends
from bowser.config.backend.aws import AwsS3BowserBackendConfig, Bucket
from bowser.config.base import BowserConfig


def test_provide_BowserBackends(tmp_path: Path):  # noqa: N802
    backend_config = [
        AwsS3BowserBackendConfig(
            region="eu-west-1",  # exercise a region other than the default
            access_key_id="testing",
            secret_access_key="testing",  # nosec B106
            buckets=[Bucket(name="test-bucket", key="")],
        )
    ]
    config = BowserConfig(dry_run=False, backends=backend_config)
    expected_backend_types = [AwsS3Backend]
    with provide_BowserBackends(
        watch_root=tmp_path, config=config, dry_run=False
    ) as actual_backends:
        actual_backend_types = [backend.__class__ for backend in actual_backends]
    # TODO: is there a stronger assertion that can be made here without baking in too
    #  many implementation details? Perhaps some custom hamcrest matchers.
    assert_that(actual_backend_types, contains_inanyorder(*expected_backend_types))


def test_provide_BowserBackends_dry_run_mode(tmp_path: Path):  # noqa: N802
    backend_config = [
        AwsS3BowserBackendConfig(
            region="eu-west-1",  # exercise a region other than the default
            access_key_id="testing",
            secret_access_key="testing",  # nosec B106
            buckets=[Bucket(name="test-bucket", key="")],
        )
    ]
    config = BowserConfig(dry_run=True, backends=backend_config)
    expected_backend_types = [AwsS3Backend]
    with provide_BowserBackends(
        watch_root=tmp_path, config=config, dry_run=True
    ) as actual_backends:
        actual_backend_types = [backend.__class__ for backend in actual_backends]
    # TODO: is there a stronger assertion that can be made here without baking in too
    #  many implementation details? Perhaps some custom hamcrest matchers.
    assert_that(actual_backend_types, contains_inanyorder(*expected_backend_types))
