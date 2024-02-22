from pathlib import Path

import pytest
from hamcrest import assert_that, equal_to

from bowser.inotify import InotifyEvent, InotifyEventData
from bowser.inotify._mapper import output_to_event_data


@pytest.mark.parametrize(
    "stdout,expected",
    [
        (
            "/some/path CREATE,ISDIR",
            InotifyEventData(
                Path("/some/path"),
                {InotifyEvent.CREATE, InotifyEvent.ISDIR},
            ),
        ),
        (
            "/some/path CLOSE_NOWRITE,CLOSE somefile.txt",
            InotifyEventData(
                Path("/some/path"),
                {InotifyEvent.CLOSE_NOWRITE, InotifyEvent.CLOSE},
                "somefile.txt",
            ),
        ),
        (
            "/some/path SURPRISE_EVENT somefile.txt",
            InotifyEventData(
                Path("/some/path"), {InotifyEvent.UNKNOWN}, "somefile.txt"
            ),
        ),
    ],
)
def test_output_to_event_data(stdout, expected: InotifyEventData):
    actual = output_to_event_data(stdout)
    assert_that(actual, equal_to(expected))
