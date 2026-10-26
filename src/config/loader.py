import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load_json(filename: str) -> list[dict[str, Any]]:
    path = DATA_DIR / filename
    with path.open(encoding="utf-8") as file:
        return json.load(file)