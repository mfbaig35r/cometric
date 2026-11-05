"""Structured issues with JSON Pointer paths so callers (and agents) can repair input."""

from __future__ import annotations

from dataclasses import dataclass, field

from .enums import Severity


def pointer(*parts: object) -> str:
    out = []
    for p in parts:
        s = str(p).replace("~", "~0").replace("/", "~1")
        out.append(s)
    return "/" + "/".join(out) if out else ""


@dataclass
class Issue:
    code: str
    severity: Severity
    message: str
    path: str = ""
    detail: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        d = {
            "code": self.code,
            "severity": str(self.severity),
            "message": self.message,
            "path": self.path,
        }
        detail = dict(self.detail)
        for key in ("expected", "example", "hint"):
            if key in detail:
                d[key] = detail.pop(key)
        if detail:
            d["detail"] = detail
        return d


class Issues(list):
    def add(self, code: str, severity: Severity, message: str, path: str = "", **detail) -> None:
        self.append(Issue(code, severity, message, path, detail))

    def error(self, code: str, message: str, path: str = "", **detail) -> None:
        self.add(code, Severity.ERROR, message, path, **detail)

    def warn(self, code: str, message: str, path: str = "", **detail) -> None:
        self.add(code, Severity.WARNING, message, path, **detail)

    def approval(self, code: str, message: str, path: str = "", **detail) -> None:
        self.add(code, Severity.APPROVAL_REQUIRED, message, path, **detail)

    def info(self, code: str, message: str, path: str = "", **detail) -> None:
        self.add(code, Severity.INFO, message, path, **detail)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == Severity.ERROR for i in self)

    def as_list(self) -> list[dict]:
        return [i.as_dict() for i in self]


class CometricError(Exception):
    """Raised when inputs cannot be evaluated; carries structured issues."""

    def __init__(self, issues: Issues, status: str = "invalid"):
        self.issues = issues
        self.status = status
        super().__init__("; ".join(f"{i.code}: {i.message} ({i.path})" for i in issues[:5]))
