import logging
import sys
from pathlib import Path

import click

from bowser import commands
from bowser.backends.di import provide_BowserBackend
from bowser.config.base import BowserConfig
from bowser.config.loader import load_app_configuration

pass_config = click.make_pass_decorator(BowserConfig, ensure=True)


@click.group
@click.option(
    "--debug",
    type=bool,
    is_flag=True,
    help="Enable debug logging. Warning: this may mean a lot of log output.",
)
@click.pass_context
def bowser(ctx: click.Context, debug: bool):  # noqa: FBT001
    """Warehouses your things for you, whether you like it or not."""
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)-8s (%(threadName)s) %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S%z",
    )
    config = load_app_configuration()
    defaults = {"watch": {"polling_interval": config.polling_interval}}
    ctx.default_map = defaults
    ctx.obj = config


@bowser.command
@click.option(
    "-p",
    "--polling-interval",
    type=int,
    default=1,
    show_default=True,
    metavar="SECONDS",
    help=(
        "The interval, in seconds, at which the provided "
        "file tree is polled for sentinel files."
    ),
)
@click.argument("root", metavar="DIR", type=click.Path(path_type=Path, exists=True))
@pass_config
def watch(config: BowserConfig, polling_interval: int, root: Path):
    """Start watching a directory."""
    backends = provide_BowserBackend(config)
    commands.watch(polling_interval=polling_interval, root=root, backends=backends)


if __name__ == "__main__":
    bowser()
