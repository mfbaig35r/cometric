"""The declarative predicate language shared by pack rules and search constraints (spec 3.5).

Grammar: {all: [P]}, {any: [P]}, {not: P}, or a leaf {path: STR, OP: VALUE} with OP in
equals, in, contains, exists, gt, lt, gte, lte. Paths are dotted; `[*]` expands a list, `*`
expands a mapping. A leaf is true when ANY matched value satisfies the operator.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

OPS = {"equals", "in", "contains", "exists", "gt", "lt", "gte", "lte"}
_SEG = re.compile(r"^([^\[\]]+)((?:\[(?:\*|\d+)\])*)$")


class PredicateError(ValueError):
    pass


def resolve(doc: Any, path: str) -> list[Any]:
    current = [doc]
    for raw in path.split("."):
        m = _SEG.match(raw)
        if not m:
            raise PredicateError(f"bad path segment {raw!r}")
        name, brackets = m.group(1), m.group(2)
        nxt: list[Any] = []
        for item in current:
            if name == "*":
                if isinstance(item, dict):
                    nxt.extend(item.values())
            elif isinstance(item, dict) and name in item:
                nxt.append(item[name])
        current = nxt
        for b in re.findall(r"\[(\*|\d+)\]", brackets):
            expanded: list[Any] = []
            for item in current:
                if isinstance(item, list):
                    if b == "*":
                        expanded.extend(item)
                    elif int(b) < len(item):
                        expanded.append(item[int(b)])
            current = expanded
    return current


def _num(v: Any) -> Decimal | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, Decimal)):
        return Decimal(v)
    if isinstance(v, str):
        try:
            return Decimal(v)
        except InvalidOperation:
            return None
    return None


def _leaf(values: list[Any], op: str, target: Any) -> bool:
    present = [v for v in values if v is not None]
    if op == "exists":
        return bool(present) if target else not present
    for v in present:
        if op in ("equals", "contains") and (v == target or str(v) == str(target)):
            return True
        if op == "in" and (v in target or str(v) in [str(t) for t in target]):
            return True
        if op in ("gt", "lt", "gte", "lte"):
            a, b = _num(v), _num(target)
            if a is None or b is None:
                continue
            if (
                (op == "gt" and a > b)
                or (op == "lt" and a < b)
                or (op == "gte" and a >= b)
                or (op == "lte" and a <= b)
            ):
                return True
    return False


def evaluate(pred: Any, doc: Any) -> bool:
    if pred is None:
        return False
    if not isinstance(pred, dict):
        raise PredicateError("predicate must be a mapping")
    if "all" in pred:
        return all(evaluate(p, doc) for p in pred["all"])
    if "any" in pred:
        return any(evaluate(p, doc) for p in pred["any"])
    if "not" in pred:
        return not evaluate(pred["not"], doc)
    if "path" not in pred:
        raise PredicateError("leaf predicate needs a path")
    ops = [k for k in pred if k != "path"]
    if len(ops) != 1 or ops[0] not in OPS:
        raise PredicateError(f"leaf needs exactly one operator from {sorted(OPS)}, got {ops}")
    return _leaf(resolve(doc, pred["path"]), ops[0], pred[ops[0]])


def check(pred: Any) -> list[str]:
    """Static check of a predicate's shape. Returns problems."""
    problems: list[str] = []
    if not isinstance(pred, dict):
        return ["predicate must be a mapping"]
    if "all" in pred or "any" in pred:
        key = "all" if "all" in pred else "any"
        if not isinstance(pred[key], list) or not pred[key]:
            problems.append(f"{key} needs a non-empty list")
        else:
            for p in pred[key]:
                problems += check(p)
        return problems
    if "not" in pred:
        return check(pred["not"])
    if "path" not in pred:
        return ["leaf predicate needs a path"]
    ops = [k for k in pred if k != "path"]
    if len(ops) != 1 or ops[0] not in OPS:
        problems.append(f"leaf needs exactly one operator from {sorted(OPS)}")
    try:
        resolve({}, pred["path"])
    except PredicateError as exc:
        problems.append(str(exc))
    return problems


def leaves(pred: Any) -> list[dict]:
    if not isinstance(pred, dict):
        return []
    for key in ("all", "any"):
        if key in pred:
            return [leaf for p in pred[key] for leaf in leaves(p)]
    if "not" in pred:
        return leaves(pred["not"])
    return [pred]
