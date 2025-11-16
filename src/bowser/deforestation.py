import logging
import sys


def configure_logging(debug: bool) -> None:  # noqa: FBT001
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s (%(threadName)s) %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S%z",
    )
