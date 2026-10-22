"""The seam between the platform and whatever actually moves money.

Business code (disbursement, STK-push reminders) only ever talks to a
`PaymentGateway`; it never knows which provider is behind it. Today there is
exactly one implementation, `SimulatedGateway` (CLAUDE.md §1 / rule #9:
everything external is simulated — it succeeds, moves no money, and says so).
A real provider (I&M, M-Pesa Daraja) becomes a second class with the same two
methods, selected by PAYMENT_GATEWAY, with no change to the callers.

Both calls take an `idempotency_key`: a real provider must treat a repeated
key as the same request, so a retry can never pay out or prompt twice.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Protocol

from .config import settings


@dataclass(frozen=True)
class GatewayResult:
    ok: bool
    reference: Optional[str]
    message: str


class PaymentGateway(Protocol):
    def send_money(self, *, idempotency_key: str, amount: Decimal, phone: str, narration: str) -> GatewayResult:
        """Pay `amount` out to `phone` (loan disbursement)."""

    def request_payment(self, *, idempotency_key: str, amount: Decimal, phone: str, account_ref: str) -> GatewayResult:
        """Prompt the owner of `phone` to pay `amount` (STK push); the money itself
        arrives later, through the bank collections API."""


class SimulatedGateway:
    def send_money(self, *, idempotency_key: str, amount: Decimal, phone: str, narration: str) -> GatewayResult:
        return GatewayResult(ok=True, reference=f"SIM-{idempotency_key}", message="Simulated disbursement (no money moved)")

    def request_payment(self, *, idempotency_key: str, amount: Decimal, phone: str, account_ref: str) -> GatewayResult:
        return GatewayResult(ok=True, reference=f"SIM-{idempotency_key}", message="Simulated STK push (nothing sent)")


def get_gateway() -> PaymentGateway:
    if settings.payment_gateway == "simulated":
        return SimulatedGateway()
    # Never fall back to "simulated" silently: an operator who configured a real
    # provider must not believe money moved when it did not.
    raise RuntimeError(f"Unknown PAYMENT_GATEWAY {settings.payment_gateway!r}; only 'simulated' is implemented")
