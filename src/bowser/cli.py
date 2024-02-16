import logging
import sys
from pathlib import Path

import click

from bowser import commands
from bowser.backends.di import provide_BowserBackends
from bowser.commands.di import provide_Executor
from bowser.config.base import DEFAULT_POLLING_INTERVAL, BowserConfig
from bowser.config.loader import load_app_configuration

pass_config = click.make_pass_decorator(BowserConfig, ensure=True)


LOGGER = logging.getLogger("bowser")


@click.group
@click.option(
    "--debug",
    type=bool,
    is_flag=True,
    help="Enable debug logging. Warning: this may mean a lot of log output.",
)
@click.pass_context
def bowser(ctx: click.Context, debug: bool) -> None:  # noqa: FBT001
    """Warehouses your things for you, whether you like it or not."""
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s (%(threadName)s) %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S%z",
    )
    LOGGER.info("Loading configuration...")
    config = load_app_configuration()
    defaults = {
        "watch": {
            "polling_interval": config.polling_interval,
            "dry_run": config.dry_run,
        }
    }
    ctx.default_map = defaults
    ctx.obj = config


@bowser.command
@click.option(
    "-p",
    "--polling-interval",
    type=int,
    default=DEFAULT_POLLING_INTERVAL,
    show_default=True,
    metavar="SECONDS",
    help=(
        "The interval, in seconds, at which the provided "
        "file tree is polled for sentinel files."
    ),
)
@click.option(
    "--dry-run",
    type=bool,
    is_flag=True,
    help="If present, AWS calls are mocked using moto and no real upload is done.",
)
@click.argument("root", metavar="DIR", type=click.Path(path_type=Path, exists=True))
@pass_config
def watch(
    config: BowserConfig,
    polling_interval: int,
    dry_run: bool,  # noqa: FBT001
    root: Path,
) -> None:
    """Start watching a directory."""
    executor = provide_Executor()
    with provide_BowserBackends(config, dry_run=dry_run) as backends:
        LOGGER.debug("Loaded the following backends: %s", ", ".join(map(str, backends)))
        commands.watch(
            root,
            polling_interval=polling_interval,
            backends=backends,
            executor=executor,
        )
        LOGGER.info("Exiting.")


if __name__ == "__main__":
    bowser()
