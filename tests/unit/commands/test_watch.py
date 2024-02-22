from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import reactivex
from hamcrest import assert_that, equal_to
from reactivex import Observable
from reactivex import operators as ops

from bowser.backends.base import BowserBackend
from bowser.commands.watch import CountWatchStrategy, SentinelWatchStrategy, execute


@pytest.fixture
def mock_tree(tmp_path: Path) -> Path:
    files = (
        Path("test1/content.txt"),
        Path("test2/subtree/content.json"),
        Path("test3/content.yml"),
    )
    for file in files:
        path = tmp_path / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    yield tmp_path


@pytest.fixture
def mock_observable_for_sentinel_strategy(mock_tree: Path) -> Observable[bytes]:
    return reactivex.of(
        f"{mock_tree / 'test1'} CREATE .bowser.ready",
        f"{mock_tree} CREATE .bowser.complete",
    ).pipe(ops.map(lambda line: line.encode()))


def test_watch_command_sentinel_strategy(
    mock_tree: Path, mock_observable_for_sentinel_strategy
):
    """Test the watch command with as near to real functionality as is pragmatic.

    The watch command blocks the main thread until it's complete, so use a background
    thread to perform the file operations that will make execution stop.
    """
    mock_backends = [MagicMock(spec=BowserBackend) for _ in range(3)]
    with patch(
        "bowser.inotify._observable.observable_background_process"
    ) as mock_observable_background_process:
        mock_observable_background_process.return_value = (
            mock_observable_for_sentinel_strategy
        )
        execute(
            mock_tree,
            backends=mock_backends,
            transform=SentinelWatchStrategy(mock_tree, sentinel=".bowser.complete"),
        )
    for mock_backend in mock_backends:
        mock_backend.upload.assert_called_once_with(mock_tree / "test1")


@pytest.fixture
def mock_observable_for_count_strategy(mock_tree: Path) -> Observable[bytes]:
    return reactivex.of(
        f"{mock_tree / 'test1'} CREATE .bowser.ready",
        f"{mock_tree / 'test2'} CREATE .bowser.ready",
        f"{mock_tree / 'test3'} CREATE .bowser.ready",
    ).pipe(ops.map(lambda line: line.encode()))


def test_watch_command_count_strategy(
    mock_tree: Path, mock_observable_for_count_strategy
):
    """Test the watch command using a count strategy.

    The fixtures used here set up an Observable that simulates the inotifywait Observable.

    The mock_observable_count_strategy simulates 3 events, so the count parameter used here
    should be <= 3.
    """
    n = 3
    mock_backend = MagicMock(spec=BowserBackend)
    with patch(
        "bowser.inotify._observable.observable_background_process"
    ) as mock_observable_background_process:
        mock_observable_background_process.return_value = (
            mock_observable_for_count_strategy
        )
        execute(mock_tree, backends=[mock_backend], transform=CountWatchStrategy(n=n))
    assert_that(mock_backend.upload.call_count, equal_to(n))
