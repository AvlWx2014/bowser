from pydantic import BaseModel

from .backend.type_alias import BowserBackendConfigT

DEFAULT_POLLING_INTERVAL = 1


class BowserConfig(BaseModel, frozen=True):
    polling_interval: int = DEFAULT_POLLING_INTERVAL
    """How often to poll the target file tree in seconds."""
    dry_run: bool = False
    """Perform a dry run of any work.

    What that means in practice is backend dependent. For example, the AWS backend uses moto to
    mock AWS calls when dry run is ``True``.
    """
    backends: list[BowserBackendConfigT]
    """A list of backend configuration objects."""
