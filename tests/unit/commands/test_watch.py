from pathlib import Path
from unittest.mock import MagicMock

from bowser.commands.di import provide_Executor
from bowser.commands.watch import SentinelWatchStrategy
from bowser.commands.watch._impl import FileSystemWatcher, execute


def test_file_system_watcherwatch_ready_tree(tmp_path: Path):
    # create test tree
    tree = tmp_path / "tree"
    tree.mkdir()

    # ensure the test file tree immediately triggers the action
    # and then exists
    (tree / ".bowser.ready").touch()
    (tmp_path / ".bowser.complete").touch()

    action = MagicMock()
    watcher = FileSystemWatcher(action=action, strategy=SentinelWatchStrategy(tmp_path))
    watcher.watch(tmp_path, polling_interval=1)
    action.assert_called_once()


def test_file_system_watcherwatch_no_ready_tree(tmp_path: Path):
    # create test tree
    tree = tmp_path / "tree"
    tree.mkdir()

    # ensure the test file tree never triggers the action and exists
    (tmp_path / ".bowser.complete").touch()

    action = MagicMock()
    watcher = FileSystemWatcher(action=action, strategy=SentinelWatchStrategy(tmp_path))
    watcher.watch(tmp_path, polling_interval=1)
    action.assert_not_called()


def test_file_system_watcherwatch_completed_tree(tmp_path: Path):
    # create test tree
    tree = tmp_path / "tree"
    tree.mkdir()

    # ensure the test file tree already triggered the action and exists
    (tree / ".bowser.complete").touch()
    (tmp_path / ".bowser.complete").touch()

    action = MagicMock()
    watcher = FileSystemWatcher(action=action, strategy=SentinelWatchStrategy(tmp_path))
    watcher.watch(tmp_path, polling_interval=1)
    action.assert_not_called()


def test_execute(tmp_path: Path):
    # create test tree
    tree = tmp_path / "tree"
    tree.mkdir()

    # ensure the test file tree immediately triggers the action
    # and then exists
    (tree / ".bowser.ready").touch()
    (tmp_path / ".bowser.complete").touch()

    mock_backend = MagicMock()
    execute(
        tmp_path,
        polling_interval=1,
        backends=[mock_backend],
        strategy=SentinelWatchStrategy(tmp_path),
        executor=provide_Executor(),
    )

    mock_backend.upload.assert_called_once()
