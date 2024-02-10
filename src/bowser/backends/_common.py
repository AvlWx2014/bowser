import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def get_metadata_for_file(path: Path) -> Mapping[str, Any]:
    metadata_path = path.with_suffix(".metadata")
    if not metadata_path.exists():
        return {}
    with metadata_path.open("r") as in_:
        return json.load(in_)
