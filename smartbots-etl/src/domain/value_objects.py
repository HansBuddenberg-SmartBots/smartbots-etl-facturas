"""Value objects del dominio."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class Money:
    """Value object para montos financieros. Siempre Decimal, nunca float."""

    amount: Decimal
    currency: str = "CLP"

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            try:
                object.__setattr__(self, "amount", Decimal(str(self.amount)))
            except (InvalidOperation, ValueError) as e:
                raise ValueError(f"Monto inválido: {self.amount}") from e

    def __add__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError(f"No se puede sumar {self.currency} con {other.currency}")
        return Money(amount=self.amount + other.amount, currency=self.currency)
