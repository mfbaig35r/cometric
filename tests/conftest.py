import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[1] / "src" / "cometric" / "examples"


def load(name: str) -> dict:
    return json.loads((EXAMPLES / f"{name}.json").read_text())


def D(v) -> Decimal:
    return Decimal(str(v))


def scenario(sid: str, assumptions: list[tuple], horizon: tuple | None = None) -> dict:
    s = {
        "id": sid,
        "assumptions": [
            {"name": n, "value": v, "unit": u, "time_period": p, "origin": "ILLUSTRATIVE"}
            for n, v, u, p in assumptions
        ],
    }
    if horizon:
        s["horizon"] = {"from": horizon[0], "to": horizon[1]}
    return s


@pytest.fixture
def spec_example():
    return copy.deepcopy(load("spec_example"))


@pytest.fixture
def case():
    def _get(letter: str) -> dict:
        return copy.deepcopy(load(f"case_{letter.lower()}"))

    return _get
