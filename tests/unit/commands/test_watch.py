from collections.abc import Generator, Iterator
from pathlib import Path
from threading import Thread
from unittest.mock import MagicMock, call, patch

import pytest
import reactivex
from hamcrest import assert_that, equal_to
from reactivex import Observable
from watchdog.events import FileCreatedEvent
from watchdog.observers import Observer as FileSystemEventLoop

from bowser.backends.base import BowserBackend
from bowser.commands.watch import CountWatchStrategy, SentinelWatchStrategy, execute
from bowser.config.base import BowserConfig


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


@pytest.fixture
def config(request) -> BowserConfig:
    return BowserConfig(dry_run=request.param, backends=[])


def dry_run_ids(flag: bool) -> str:  # noqa: FBT001
    return "dry_run" if flag else "actual"


@pytest.mark.parametrize("config", [True, False], indirect=True, ids=dry_run_ids)
def test_watch_command_sentinel_strategy(
    mock_tree: Path,
    config: BowserConfig,
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
            config=config,
            backends=mock_backends,
            transform=SentinelWatchStrategy(mock_tree, sentinel=".bowser.complete"),
            preempt_sentinel=mock_tree / ".bowser.abort",
        )
    for mock_backend in mock_backends:
        target = mock_backend.upload_dry_run if config.dry_run else mock_backend.upload
        target.assert_called_once_with(mock_tree / "test1")


@pytest.fixture
def mock_preempted_observable_for_sentinel_strategy(
    mock_tree: Path,
) -> Observable[FileCreatedEvent]:
    return reactivex.of(
        FileCreatedEvent(src_path=str(mock_tree / ".bowser.abort")),
        FileCreatedEvent(src_path=str(mock_tree / "test1" / ".bowser.ready")),
        FileCreatedEvent(src_path=str(mock_tree / ".bowser.complete")),
    )


@pytest.mark.parametrize("config", [True, False], indirect=True, ids=dry_run_ids)
def test_watch_command_preempt_sentinel_strategy(
    mock_tree: Path,
    config: BowserConfig,
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
            config=config,
            backends=mock_backends,
            transform=SentinelWatchStrategy(mock_tree, sentinel=".bowser.complete"),
            preempt_sentinel=mock_tree / ".bowser.abort",
        )

    for mock_backend in mock_backends:
        target = mock_backend.upload_dry_run if config.dry_run else mock_backend.upload
        target.assert_not_called()


@pytest.fixture
def mock_observable_for_count_strategy(mock_tree: Path) -> Observable[FileCreatedEvent]:
    return reactivex.of(
        FileCreatedEvent(src_path=str(mock_tree / "test1" / ".bowser.ready")),
        FileCreatedEvent(src_path=str(mock_tree / "test2" / ".bowser.ready")),
        FileCreatedEvent(src_path=str(mock_tree / "test3" / ".bowser.ready")),
    )


@pytest.mark.parametrize("config", [True, False], indirect=True, ids=dry_run_ids)
def test_watch_command_count_strategy(
    mock_tree: Path,
    config: BowserConfig,
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
            config=config,
            backends=[mock_backend],
            transform=CountWatchStrategy(n=n),
            preempt_sentinel=mock_tree / ".bowser.abort",
        )
    target = mock_backend.upload_dry_run if config.dry_run else mock_backend.upload
    assert_that(target.call_count, equal_to(n))


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


@pytest.mark.parametrize("config", [True, False], indirect=True, ids=dry_run_ids)
def test_watch_command_preempt_count_strategy(
    mock_tree: Path,
    config: BowserConfig,
    mock_preempted_observable_for_count_strategy: Observable[FileCreatedEvent],
    mock_watchdog_observer: FileSystemEventLoop,
):
    n = 3
    mock_backend = MagicMock(spec=BowserBackend)
    with patch("bowser.commands.watch._impl.WatchdogEventObservable") as mock_upstream:
        mock_upstream.return_value = mock_preempted_observable_for_count_strategy
        execute(
            mock_tree,
            config=config,
            backends=[mock_backend],
            transform=CountWatchStrategy(n=n),
            preempt_sentinel=mock_tree / ".bowser.abort",
        )
    target = mock_backend.upload_dry_run if config.dry_run else mock_backend.upload
    assert_that(target.call_count, equal_to(1))


@pytest.fixture
def mock_preempted_observable_custom_sentinel(
    mock_tree: Path,
) -> Observable[FileCreatedEvent]:
    return reactivex.of(
        FileCreatedEvent(src_path=str(mock_tree / "test1" / ".bowser.abort")),
        FileCreatedEvent(src_path=str(mock_tree / "test1" / ".bowser.ready")),
        FileCreatedEvent(src_path=str(mock_tree / ".bowser.complete")),
    )


@pytest.mark.parametrize("config", [True, False], indirect=True, ids=dry_run_ids)
def test_watch_command_preempt_custom_sentinel(
    mock_tree: Path,
    config: BowserConfig,
    mock_preempted_observable_custom_sentinel: Observable[FileCreatedEvent],
    mock_watchdog_observer: FileSystemEventLoop,
):
    mock_backends = [MagicMock(spec=BowserBackend) for _ in range(3)]
    with patch("bowser.commands.watch._impl.WatchdogEventObservable") as mock_upstream:
        mock_upstream.return_value = mock_preempted_observable_custom_sentinel
        execute(
            mock_tree,
            config=config,
            backends=mock_backends,
            transform=SentinelWatchStrategy(mock_tree, sentinel=".bowser.complete"),
            preempt_sentinel=mock_tree / "test1" / ".bowser.abort",
        )
    for mock_backend in mock_backends:
        target = mock_backend.upload_dry_run if config.dry_run else mock_backend.upload
        target.assert_not_called()


@pytest.fixture
def mock_external_process(mock_tree: Path) -> Thread:
    class ExternalProcess(Thread):
        def __init__(self, write_to: Path) -> None:
            super().__init__()
            self._write_to = write_to

        def run(self) -> None:
            parent = self._write_to / "mock_external_process"
            parent.mkdir(parents=True, exist_ok=True)
            for file in ("test1.txt", "test2.json", "test3.yml", ".bowser.ready"):
                (parent / file).touch()

    return ExternalProcess(mock_tree)


@pytest.mark.parametrize("config", [True, False], indirect=True, ids=dry_run_ids)
def test_watch_command_simulate_restart(
    mock_tree: Path,
    config: BowserConfig,
    mock_external_process: Thread,
) -> None:
    mock_backend = MagicMock(spec=BowserBackend)
    # pretend we have restarted and have to pick up on events we may have missed
    for subdir in ("test1", "test2", "test3"):
        (mock_tree / subdir / ".bowser.ready").touch()

    execute(
        mock_tree,
        config=config,
        backends=[mock_backend],
        transform=CountWatchStrategy(n=4),
        preempt_sentinel=mock_tree / ".bowser.abort",
        on_start=mock_external_process.start,
    )
    mock_external_process.join(timeout=5)

    target = mock_backend.upload_dry_run if config.dry_run else mock_backend.upload
    target.assert_has_calls(
        [
            call(mock_tree / node)
            for node in ("mock_external_process", "test1", "test2", "test3")
        ],
        any_order=True,
    )
