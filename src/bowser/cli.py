import logging
import sys
from pathlib import Path
from typing import Never

import click

from bowser import commands
from bowser.backends.di import provide_BowserBackends
from bowser.commands.di import provide_Executor
from bowser.commands.watch import (
    CountWatchStrategy,
    SentinelWatchStrategy,
    WatchStrategy,
    WatchType,
)
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
@click.option(
    "--strategy",
    metavar="STRATEGY",
    type=click.Choice(WatchType.values(), case_sensitive=False),
    default=WatchType.SENTINEL.value,
    callback=lambda ctx, param, value: WatchType[value.upper()],
    show_default=True,
    help="Controls what type of event signals the watch command to stop.",
)
@click.option(
    "-n",
    "--count",
    type=int,
    help=(
        f"If the '{WatchType.COUNT!s}' watch strategy is chosen, this specifies "
        "how many completion events to wait for before stopping. "
        "Must be >= 1."
    ),
)
@click.argument("root", metavar="DIR", type=click.Path(path_type=Path, exists=True))
@pass_config
def watch(
    config: BowserConfig,
    polling_interval: int,
    dry_run: bool,  # noqa: FBT001
    strategy: WatchType,
    count: int | None,
    root: Path,
) -> None:
    """Watch subdirectories of the given directory and upload them once they're ready.

    This is not recursive - only direct child directories are watched.
    """
    executor = provide_Executor()
    watch_strategy: WatchStrategy
    match strategy:
        case WatchType.SENTINEL:
            sentinel = ".bowser.complete"
            watch_strategy = SentinelWatchStrategy(root, sentinel=sentinel)
        case WatchType.COUNT:
            if count is None or count <= 0:
                print_help_and_exit()
            watch_strategy = CountWatchStrategy(root, limit=count)
        case _:
            raise RuntimeError(
                "Exhaustive match on enum type 'WatchType' failed to match."
                f"Unknown value: {watch}"
            )
    with provide_BowserBackends(config, dry_run=dry_run) as backends:
        dry_run_mode = f"dry_run mode: {'on' if dry_run else 'off'}"
        LOGGER.info(
            "Loaded the following backends (%s): %s",
            dry_run_mode,
            ", ".join(map(str, backends)),
        )
        commands.watch(
            root,
            polling_interval=polling_interval,
            backends=backends,
            strategy=watch_strategy,
            executor=executor,
        )
    LOGGER.info("Exiting.")
    click.get_current_context().exit()


def print_help_and_exit() -> Never:
    context = click.get_current_context()
    click.echo(context.get_help())
    context.exit(1)


if __name__ == "__main__":
    bowser()
