from typing import Literal

from pydantic import BaseModel, ConfigDict

from ...extensions import Literally


class BowserBackendConfig(BaseModel):
    model_config: ConfigDict = ConfigDict(frozen=True)
    """Note: this is Pydantic magic to configure your models e.g. make them frozen.

    Using ``frozen=True`` as an instance attribute ensures a ``__hash__` method is
    generated for the model, allowing it to be used in conjunction with things like
    sets, dicts, and functools.cache.
    """
    kind: Literal["NotImplemented"] = Literally("NotImplemented")
    """The label for this kind of data source.

    This is primarily for convenience at runtime e.g. for logging messages that
    don't want to have to customize the printed label based on type.
    """
