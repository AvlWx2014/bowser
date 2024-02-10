from pydantic import BaseModel


class BowserBackendConfig(BaseModel, frozen=True):
    kind: str
