from pathlib import Path
from unittest.mock import MagicMock

from bowser.commands.watch import FileSystemWatcher, execute


def test_FileSystemWatcher_watch_ready_tree(tmp_path: Path):
    # create test tree
    tree = tmp_path / "tree"
    tree.mkdir()

    # ensure the test file tree immediately triggers the action
    # and then exists
    (tree / ".bowser.ready").touch()
    (tmp_path / ".bowser.complete").touch()

    action = MagicMock()
    watcher = FileSystemWatcher(action=action)
    watcher.watch(tmp_path, polling_interval=1)
    action.assert_called_once()


def test_FileSystemWatcher_watch_no_ready_tree(tmp_path: Path):
    # create test tree
    tree = tmp_path / "tree"
    tree.mkdir()

    # ensure the test file tree never triggers the action and exists
    (tmp_path / ".bowser.complete").touch()

    action = MagicMock()
    watcher = FileSystemWatcher(action=action)
    watcher.watch(tmp_path, polling_interval=1)
    action.assert_not_called()


def test_FileSystemWatcher_watch_completed_tree(tmp_path: Path):
    # create test tree
    tree = tmp_path / "tree"
    tree.mkdir()

    # ensure the test file tree already triggered the action and exists
    (tree / ".bowser.complete").touch()
    (tmp_path / ".bowser.complete").touch()

    action = MagicMock()
    watcher = FileSystemWatcher(action=action)
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
        polling_interval=1,
        root=tmp_path,
        backends=[mock_backend]
    )

    mock_backend.upload.assert_called_once()
