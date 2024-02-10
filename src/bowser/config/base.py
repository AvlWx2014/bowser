
from pydantic import BaseModel, ConfigDict


class BowserConfig(BaseModel):
    model_config: ConfigDict = ConfigDict(frozen=True)
    """Note: this is Pydantic magic to configure your models e.g. make them frozen.

    Using ``frozen=True`` as an instance attribute ensures a ``__hash__` method is
    generated for the model, allowing it to be used in conjunction with things like
    sets, dicts, and functools.cache.
    """
    polling_interval: int = 1
    """How often to poll the target file tree in seconds."""
    strict: bool = True
    """If ``False``, errors are ignored. Otherwise, they will be raised."""
    verbose: bool = False
    """If ``True``, then logging will be set to the most verbose level."""
