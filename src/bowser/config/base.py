from pydantic import BaseModel

from .backend.type_alias import BowserBackendConfigT


class BowserConfig(BaseModel, frozen=True):
    dry_run: bool = False
    """Perform a dry run of any work.

    What that means in practice is backend dependent. For example, the AWS backend uses moto to
    mock AWS calls when dry run is ``True``.
    """
    backends: list[BowserBackendConfigT]
    """A list of backend configuration objects."""
