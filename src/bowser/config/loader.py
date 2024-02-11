from __future__ import annotations

import logging
import os
import tomllib as toml
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Any

from .base import BowserConfig

_XDG_CONFIG_HOME = os.getenv("XDG_CONFIG_HOME")
_XDG_CONFIG_PATH = (
    Path(_XDG_CONFIG_HOME) if _XDG_CONFIG_HOME else Path.home() / ".config"
)

_CHECK_PATHS = (Path("/etc/bowser.toml"), _XDG_CONFIG_PATH / "bowser/bowser.toml")
"""Default set of paths to check for configuration files.

Any configuration files found in these locations are merged together, with those appearing later
taking precedence over those appearing earlier.
"""


LOGGER = logging.getLogger("bowser")


def load_app_configuration(
    check_paths: Collection[Path] = _CHECK_PATHS,
) -> BowserConfig:
    """Load configuration data from all ``bowser.toml`` files in ``check_paths``.

    Each path in ``check_paths`` can be a path to the parent directory of a ``bowser.toml`` file,
    or the path to the ``bowser.toml`` file itself.

    Configuration is merged together in order of appearance, where configuration files
    appearing later in ``check_paths`` take precedence over those appearing earlier.

    Parameters:
        check_paths: The paths to check for configuration files. Any configuration files named
            `bowser.toml` are loaded and merged together in reverse priority order. In other words,
            any configuration files found later in ``check_paths`` take precedence over those found
            earlier in ``check_paths``.
    """
    logger = logging.getLogger("bowser")
    logger.info("Looking for configuration files %s", ", ".join(map(str, check_paths)))
    candidate_files = []
    for path in check_paths:
        if path.name != "bowser.toml":
            path /= "bowser.toml"
        candidate_files.append(path)
    raw = _load_raw_configuration(candidate_files)
    return BowserConfig.model_validate(raw.get("bowser", {}))


def _load_raw_configuration(
    check_paths: Collection[Path],
) -> Mapping[str, Any]:
    config: Mapping[str, Any] = {}
    for path in check_paths:
        if path.exists():
            with path.open("rb") as in_:
                intermediate: Mapping[str, Any] = toml.load(in_)
            config = _merge_configuration(config, intermediate)
    return config


def _merge_configuration(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Merge two configuration maps recursively.

    Keys that are in either ``left`` or ``right``, but not both, appear in the final merged
    configuration.

    Keys that are in both ``left`` and ``right`` are merged as follows:
      - The value from ``right`` takes precedence _unless_ it is a map, in which case the values
        from ``left`` and ``right`` are merged by calling this function recursively.

    Put another way, scalar and array values in ``right`` that are also in ``left``, completely
    override the value in ``left`` and mappings are merged recursively.
    """
    merged = {**left}
    for k, v in right.items():
        if k in merged and isinstance(v, Mapping):
            # assumes that if right[k] is a mapping, left[k] is also a mapping
            # i.e. that both left and right follow the same schema
            v = _merge_configuration(merged[k], v)
        merged[k] = v
    return merged
