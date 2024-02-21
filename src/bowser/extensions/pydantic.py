from typing import Any

from pydantic import Field


def Literally(value: Any) -> Any:  # noqa: N802
    """Shortcut for defining fields in Pydantic BaseModels that are just static strings."""
    return Field(default=value, init_var=False, frozen=True)
