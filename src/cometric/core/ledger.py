"""Entitlement ledger: grants, FIFO consumption, rollover, expiry (spec 4.4, T-006)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .enums import RolloverPolicy
from .models import Entitlement
from .money import ZERO
from .periods import Month, month_str


@dataclass
class Lot:
    lot_id: str
    origin: str  # GRANT or ROLLOVER_IN
    period: tuple
    quantity: Decimal
    remaining: Decimal
    source_lot: str | None = None


@dataclass
class LedgerEntry:
    period: str
    entitlement_id: str
    entry_type: str
    quantity: Decimal
    lot_id: str
    accumulation_period: str
    contract_version: str
    unit: str

    def as_dict(self) -> dict:
        return {
            "period": self.period,
            "entitlement_id": self.entitlement_id,
            "entry_type": self.entry_type,
            "quantity": self.quantity,
            "lot_id": self.lot_id,
            "accumulation_period": self.accumulation_period,
            "contract_version": self.contract_version,
            "unit": self.unit,
        }


@dataclass
class EntitlementLedger:
    entitlement: Entitlement
    lots: list[Lot] = field(default_factory=list)
    entries: list[LedgerEntry] = field(default_factory=list)
    current_period: tuple | None = None
    last_month: Month | None = None
    version_id: str = ""
    _seq: int = 0

    def _entry(self, m: Month, kind: str, qty: Decimal, lot: Lot) -> None:
        self.entries.append(
            LedgerEntry(
                month_str(m),
                self.entitlement.id,
                kind,
                qty,
                lot.lot_id,
                str(self.entitlement.accumulation_period),
                self.version_id,
                self.entitlement.unit,
            )
        )

    def start_month(self, m: Month, key: tuple, entitlement: Entitlement, version_id: str) -> None:
        """Open the accumulation period for month m, closing the previous one if it changed."""
        self.entitlement = entitlement
        self.version_id = version_id
        if key != self.current_period:
            if self.current_period is not None and self.last_month is not None:
                self._close(self.last_month, final=False)
            self.current_period = key
            self._seq += 1
            lot = Lot(
                f"{entitlement.id}#{self._seq}",
                "GRANT",
                key,
                entitlement.included_quantity,
                entitlement.included_quantity,
            )
            self.lots.append(lot)
            self._entry(m, "GRANT", entitlement.included_quantity, lot)
        self.last_month = m

    def consume(self, m: Month, quantity: Decimal) -> tuple[Decimal, Decimal]:
        """FIFO consumption: rolled-in lots first, then the current grant. Returns (in_allowance, excess)."""
        remaining = quantity
        open_lots = sorted(
            (lot for lot in self.lots if lot.remaining > 0),
            key=lambda lot: (lot.origin != "ROLLOVER_IN", lot.lot_id),
        )
        for lot in open_lots:
            if remaining <= 0:
                break
            take = min(lot.remaining, remaining)
            lot.remaining -= take
            remaining -= take
            self._entry(m, "CONSUME", take, lot)
        return quantity - remaining, remaining

    def _close(self, m: Month, final: bool) -> None:
        policy = self.entitlement.rollover.policy
        ceiling = self.entitlement.rollover.ceiling
        for lot in list(self.lots):
            if lot.remaining <= 0:
                continue
            roll = ZERO
            if not final and policy == RolloverPolicy.TERM:
                roll = lot.remaining
            elif not final and policy == RolloverPolicy.NEXT_PERIOD and lot.origin == "GRANT":
                roll = lot.remaining if ceiling is None else min(lot.remaining, ceiling)
            expire = lot.remaining - roll
            if roll > 0:
                self._seq += 1
                self._entry(m, "ROLLOVER_OUT", roll, lot)
                new = Lot(
                    f"{self.entitlement.id}#{self._seq}",
                    "ROLLOVER_IN",
                    ("next",),
                    roll,
                    roll,
                    lot.lot_id,
                )
                self.lots.append(new)
                self._entry(m, "ROLLOVER_IN", roll, new)
            if expire > 0:
                self._entry(m, "EXPIRE", expire, lot)
            lot.remaining = ZERO

    def finish(self, m: Month, engagement_ended: bool) -> None:
        """Close at the end of the run. Expire at engagement end; otherwise leave lots open."""
        if engagement_ended and self.last_month is not None:
            self._close(self.last_month, final=True)

    def granted(self) -> Decimal:
        return sum((e.quantity for e in self.entries if e.entry_type == "GRANT"), ZERO)

    def consumed(self) -> Decimal:
        return sum((e.quantity for e in self.entries if e.entry_type == "CONSUME"), ZERO)

    def check_invariant(self) -> list[str]:
        """Every lot: in = consumed + rolled out + expired + still open (T-006)."""
        problems = []
        for lot in self.lots:
            out = sum(
                (
                    e.quantity
                    for e in self.entries
                    if e.lot_id == lot.lot_id
                    and e.entry_type in {"CONSUME", "ROLLOVER_OUT", "EXPIRE"}
                ),
                ZERO,
            )
            if out + lot.remaining != lot.quantity:
                problems.append(
                    f"lot {lot.lot_id}: {lot.quantity} in, {out} out, {lot.remaining} open"
                )
        return problems
