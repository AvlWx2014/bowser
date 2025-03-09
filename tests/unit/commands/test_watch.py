from collections.abc import Generator, Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import reactivex
from hamcrest import assert_that, equal_to
from reactivex import Observable
from watchdog.events import FileCreatedEvent
from watchdog.observers import Observer as FileSystemEventLoop

from bowser.backends.base import BowserBackend
from bowser.commands.watch import CountWatchStrategy, SentinelWatchStrategy, execute


@pytest.fixture
def mock_tree(tmp_path: Path) -> Generator[Path, None, None]:
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
def mock_watchdog_observer() -> Iterator[FileSystemEventLoop]:
    with patch(
        "bowser.commands.watch._impl.FileSystemEventLoop", spec=FileSystemEventLoop
    ) as mock_:
        yield mock_


@pytest.fixture
def mock_observable_for_sentinel_strategy(
    mock_tree: Path,
) -> Observable[FileCreatedEvent]:
    return reactivex.of(
        FileCreatedEvent(src_path=str(mock_tree / "test1" / ".bowser.ready")),
        FileCreatedEvent(src_path=str(mock_tree / ".bowser.complete")),
    )


def test_watch_command_sentinel_strategy(
    mock_tree: Path,
    mock_observable_for_sentinel_strategy: Observable[FileCreatedEvent],
    mock_watchdog_observer: FileSystemEventLoop,
):
    """Test the watch command with the --sentinel strategy.

    The watch command blocks the main thread until execution is complete denoted
    by the appearance of the sentinel file.
    """
    mock_backends = [MagicMock(spec=BowserBackend) for _ in range(3)]
    with patch("bowser.commands.watch._impl.WatchdogEventObservable") as mock_upstream:
        mock_upstream.return_value = mock_observable_for_sentinel_strategy
        execute(
            mock_tree,
            backends=mock_backends,
            transform=SentinelWatchStrategy(mock_tree, sentinel=".bowser.complete"),
            preempt_sentinel=mock_tree / ".bowser.abort",
        )
    for mock_backend in mock_backends:
        mock_backend.upload.assert_called_once_with(mock_tree / "test1")


@pytest.fixture
def mock_preempted_observable_for_sentinel_strategy(
    mock_tree: Path,
) -> Observable[FileCreatedEvent]:
    return reactivex.of(
        FileCreatedEvent(src_path=str(mock_tree / ".bowser.abort")),
        FileCreatedEvent(src_path=str(mock_tree / "test1" / ".bowser.ready")),
        FileCreatedEvent(src_path=str(mock_tree / ".bowser.complete")),
    )


def test_watch_command_preempt_sentinel_strategy(
    mock_tree: Path,
    mock_preempted_observable_for_sentinel_strategy: Observable[FileCreatedEvent],
    mock_watchdog_observer: FileSystemEventLoop,
):
    """Test the watch command with the --sentinel strategy.

    This tests that the event stream is preempted by the PreemptObservable when
    the sentinel file appears no matter what events are yet to come.
    """
    mock_backends = [MagicMock(spec=BowserBackend) for _ in range(3)]
    with patch("bowser.commands.watch._impl.WatchdogEventObservable") as mock_upstream:
        mock_upstream.return_value = mock_preempted_observable_for_sentinel_strategy
        execute(
            mock_tree,
            backends=mock_backends,
            transform=SentinelWatchStrategy(mock_tree, sentinel=".bowser.complete"),
            preempt_sentinel=mock_tree / ".bowser.abort",
        )
    for mock_backend in mock_backends:
        mock_backend.upload.assert_not_called()


@pytest.fixture
def mock_observable_for_count_strategy(mock_tree: Path) -> Observable[FileCreatedEvent]:
    return reactivex.of(
        FileCreatedEvent(src_path=str(mock_tree / "test1" / ".bowser.ready")),
        FileCreatedEvent(src_path=str(mock_tree / "test2" / ".bowser.ready")),
        FileCreatedEvent(src_path=str(mock_tree / "test3" / ".bowser.ready")),
    )


def test_watch_command_count_strategy(
    mock_tree: Path,
    mock_observable_for_count_strategy: Observable[FileCreatedEvent],
    mock_watchdog_observer: FileSystemEventLoop,
):
    """Test the watch command using a count strategy.

    The fixtures used here set up an Observable that simulates the inotifywait Observable.

    The mock_observable_count_strategy simulates 3 events, so the count parameter used here
    should be <= 3.
    """
    n = 3
    mock_backend = MagicMock(spec=BowserBackend)
    with patch("bowser.commands.watch._impl.WatchdogEventObservable") as mock_upstream:
        mock_upstream.return_value = mock_observable_for_count_strategy
        execute(
            mock_tree,
            backends=[mock_backend],
            transform=CountWatchStrategy(n=n),
            preempt_sentinel=mock_tree / ".bowser.abort",
        )
    assert_that(mock_backend.upload.call_count, equal_to(n))


@pytest.fixture
def mock_preempted_observable_for_count_strategy(
    mock_tree: Path,
) -> Observable[FileCreatedEvent]:
    return reactivex.of(
        FileCreatedEvent(src_path=str(mock_tree / "test1" / ".bowser.ready")),
        FileCreatedEvent(src_path=str(mock_tree / ".bowser.abort")),
        FileCreatedEvent(src_path=str(mock_tree / "test2" / ".bowser.ready")),
        FileCreatedEvent(src_path=str(mock_tree / "test3" / ".bowser.ready")),
    )


def test_watch_command_preempt_count_strategy(
    mock_tree: Path,
    mock_preempted_observable_for_count_strategy: Observable[FileCreatedEvent],
    mock_watchdog_observer: FileSystemEventLoop,
):
    n = 3
    mock_backend = MagicMock(spec=BowserBackend)
    with patch("bowser.commands.watch._impl.WatchdogEventObservable") as mock_upstream:
        mock_upstream.return_value = mock_preempted_observable_for_count_strategy
        execute(
            mock_tree,
            backends=[mock_backend],
            transform=CountWatchStrategy(n=n),
            preempt_sentinel=mock_tree / ".bowser.abort",
        )
    assert_that(mock_backend.upload.call_count, equal_to(1))


@pytest.fixture
def mock_preempted_observable_custom_sentinel(
    mock_tree: Path,
) -> Observable[FileCreatedEvent]:
    return reactivex.of(
        FileCreatedEvent(src_path=str(mock_tree / "test1" / ".bowser.abort")),
        FileCreatedEvent(src_path=str(mock_tree / "test1" / ".bowser.ready")),
        FileCreatedEvent(src_path=str(mock_tree / ".bowser.complete")),
    )


def test_watch_command_preempt_custom_sentinel(
    mock_tree: Path,
    mock_preempted_observable_custom_sentinel: Observable[FileCreatedEvent],
    mock_watchdog_observer: FileSystemEventLoop,
):
    mock_backends = [MagicMock(spec=BowserBackend) for _ in range(3)]
    with patch("bowser.commands.watch._impl.WatchdogEventObservable") as mock_upstream:
        mock_upstream.return_value = mock_preempted_observable_custom_sentinel
        execute(
            mock_tree,
            backends=mock_backends,
            transform=SentinelWatchStrategy(mock_tree, sentinel=".bowser.complete"),
            preempt_sentinel=mock_tree / "test1" / ".bowser.abort",
        )
    for mock_backend in mock_backends:
        mock_backend.upload.assert_not_called()
