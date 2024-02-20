from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from hamcrest import assert_that, equal_to

from bowser.config.backend.aws import AwsS3BowserBackendConfig, Bucket
from bowser.config.base import BowserConfig
from bowser.config.loader import _merge_configuration, load_app_configuration

HERE = Path(__file__).parent
DATA = HERE / "data"


def test_load_app_configuration():
    expected = BowserConfig(
        polling_interval=311,
        backends=[
            AwsS3BowserBackendConfig(
                region="eu-west-1",
                access_key_id="access key",
                secret_access_key="secret squirrel stuff",  # nosec B106
                buckets=[Bucket(name="bucket", key="some/root/key")],
            )
        ],
    )
    actual = load_app_configuration(check_paths=(DATA,))
    assert_that(actual, equal_to(expected))


@pytest.mark.parametrize(
    "left,right,expected",
    [
        (
            {
                "key1": "left",
                "key2": [1, 2, 3, 4],
                "key3": {"nested1": "left", "nested2": "left"},
            },
            {},
            {
                "key1": "left",
                "key2": [1, 2, 3, 4],
                "key3": {"nested1": "left", "nested2": "left"},
            },
        ),
        (
            {},
            {
                "key1": "right",
                "key2": [1, 2, 3, 4],
                "key3": {"nested1": "right", "nested2": "right"},
            },
            {
                "key1": "right",
                "key2": [1, 2, 3, 4],
                "key3": {"nested1": "right", "nested2": "right"},
            },
        ),
        (
            {
                "key1": "left-only",
                "key2": [1, 2, 3, 4],
                "key3": {"nested1": "left", "nested2": "left"},
            },
            {
                "key4": "right-only",
                "key2": [4, 3, 2, 1],
                "key3": {"nested1": "right"},
            },
            {
                "key1": "left-only",
                "key2": [4, 3, 2, 1],
                "key3": {"nested1": "right", "nested2": "left"},
                "key4": "right-only",
            },
        ),
    ],
)
def test__merge_configuration(
    left: Mapping[str, Any], right: Mapping[str, Any], expected: Mapping[str, Any]
):
    actual = _merge_configuration(left, right)
    assert_that(actual, equal_to(expected))
