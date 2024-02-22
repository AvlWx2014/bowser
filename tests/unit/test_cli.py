from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner
from hamcrest import assert_that, equal_to

from bowser.cli import bowser
from bowser.config.loader import load_app_configuration

HERE = Path(__file__).parent
DATA = HERE / "data"


def test_cli(tmp_path: Path) -> None:
    configuration = load_app_configuration(check_paths=(DATA,))
    mock_args = ["watch", str(tmp_path)]
    with (
        patch("bowser.cli.commands.watch") as mock_watch_command,
        patch("bowser.cli.load_app_configuration") as mock_load_app_configuration,
    ):
        mock_load_app_configuration.return_value = configuration
        runner = CliRunner()
        with runner.isolated_filesystem(tmp_path):
            result = runner.invoke(bowser, args=mock_args)
    assert_that(result.exit_code, equal_to(0))
    mock_watch_command.assert_called_once()
