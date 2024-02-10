from pydantic import BaseModel

from .backend.type_alias import BowserBackendConfigT

DEFAULT_POLLING_INTERVAL = 1


class BowserConfig(BaseModel, frozen=True):
    polling_interval: int = DEFAULT_POLLING_INTERVAL
    """How often to poll the target file tree in seconds."""
    backends: list[BowserBackendConfigT]
    """A list of backend configuration objects."""
