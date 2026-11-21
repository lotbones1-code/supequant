"""Strict immutable inputs for the offline spot engine; no I/O at import."""

from contextlib import contextmanager
from dataclasses import dataclass, fields
from decimal import Context, Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, localcontext
import re
from typing import Iterator


@contextmanager
def decimal_scope() -> Iterator[Context]:
    """Do not let an unrelated strategy change money arithmetic's precision."""
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)) as context:
        yield context


def D(value: str | int | Decimal) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError("amounts must be decimal strings, integers, or Decimal; floats are forbidden")
    try:
        result = Decimal(value)
    except Exception as exc:
        raise ValueError("invalid decimal amount") from exc
    if not result.is_finite():
        raise ValueError("amounts must be finite")
    # Bound untrusted inputs before arithmetic or formatting can become expensive.
    if len(result.as_tuple().digits) > 50 or (result and not -48 <= result.adjusted() <= 24):
        raise ValueError("amount exceeds the supported decimal range")
    return result


def floor_step(value: Decimal, step: Decimal) -> Decimal:
    value, step = D(value), D(step)
    if value < 0 or step <= 0:
        raise ValueError("rounding requires nonnegative value and positive step")
    with decimal_scope():
        return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def ceil_step(value: Decimal, step: Decimal) -> Decimal:
    value, step = D(value), D(step)
    if value < 0 or step <= 0:
        raise ValueError("rounding requires nonnegative value and positive step")
    with decimal_scope():
        return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


def validate_timestamp(value: int) -> int:
    if type(value) is not int or not 0 <= value <= 253402214400:
        raise ValueError("timestamp must be nonnegative whole UTC epoch seconds")
    return value


def validate_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value):
        raise ValueError("invalid identifier")
    return value


def _positive_fields(instance: object, names: tuple[str, ...], *, allow_zero: bool = False) -> None:
    for name in names:
        value = D(getattr(instance, name))
        if value < 0 or (value == 0 and not allow_zero):
            raise ValueError(f"{name} must be {'nonnegative' if allow_zero else 'positive'}")
        object.__setattr__(instance, name, value)


@dataclass(frozen=True)
class Product:
    product_id: str
    base_currency: str
    quote_currency: str
    base_increment: Decimal
    quote_increment: Decimal
    price_increment: Decimal
    base_min_size: Decimal
    base_max_size: Decimal
    quote_min_size: Decimal
    quote_max_size: Decimal

    def __post_init__(self) -> None:
        for currency in (self.base_currency, self.quote_currency):
            if not isinstance(currency, str) or not re.fullmatch(r"[A-Z0-9]{1,16}", currency):
                raise ValueError("invalid currency identifier")
        if self.base_currency == self.quote_currency or self.product_id != f"{self.base_currency}-{self.quote_currency}":
            raise ValueError("product must be an explicit base-quote spot pair")
        _positive_fields(self, tuple(f.name for f in fields(self) if f.name not in {
            "product_id", "base_currency", "quote_currency"
        }))
        if self.base_min_size > self.base_max_size or self.quote_min_size > self.quote_max_size:
            raise ValueError("product minimum exceeds maximum")

    @classmethod
    def from_coinbase(cls, payload: dict) -> "Product":
        """Validate a saved public-product response; never fetch an endpoint."""
        if not isinstance(payload, dict) or payload.get("product_type") != "SPOT":
            raise ValueError("only an explicitly identified SPOT product is supported")
        if not isinstance(payload.get("status"), str) or payload["status"].lower() != "online":
            raise ValueError("product snapshot must be online")
        flags = ("is_disabled", "trading_disabled", "cancel_only", "limit_only", "post_only", "auction_mode", "view_only")
        if any(payload.get(name) is not False for name in flags):
            raise ValueError("missing or restricted product status; market replay is blocked")
        try:
            return cls(
                product_id=payload["product_id"], base_currency=payload["base_currency_id"],
                quote_currency=payload["quote_currency_id"],
                **{name: D(payload[name]) for name in (
                    "base_increment", "quote_increment", "price_increment", "base_min_size",
                    "base_max_size", "quote_min_size", "quote_max_size"
                )},
            )
        except (KeyError, TypeError) as exc:
            raise ValueError("incomplete product snapshot") from exc

    def validate_order(self, quantity: Decimal, price: Decimal) -> None:
        quantity, price = D(quantity), D(price)
        if quantity <= 0 or price <= 0:
            raise ValueError("order size and price must be positive")
        with decimal_scope():
            if floor_step(quantity, self.base_increment) != quantity:
                raise ValueError("quantity does not match base increment")
            if floor_step(price, self.price_increment) != price:
                raise ValueError("price does not match price increment")
            if not self.base_min_size <= quantity <= self.base_max_size:
                raise ValueError("quantity outside product bounds")
            if not self.quote_min_size <= quantity * price <= self.quote_max_size:
                raise ValueError("notional outside product bounds")

    def to_dict(self) -> dict[str, str]:
        return {f.name: str(getattr(self, f.name)) for f in fields(self)}


@dataclass(frozen=True)
class Candle:
    product_id: str
    start: int
    interval: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        validate_id(self.product_id)
        validate_timestamp(self.start)
        if type(self.interval) is not int or self.interval <= 0 or self.start % self.interval:
            raise ValueError("candle must lie on a positive whole-second interval grid")
        validate_timestamp(self.end)
        _positive_fields(self, ("open", "high", "low", "close"))
        _positive_fields(self, ("volume",), allow_zero=True)
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError("invalid OHLC ordering")

    @property
    def end(self) -> int:
        return self.start + self.interval


@dataclass(frozen=True)
class Order:
    order_id: str
    product_id: str
    side: str
    quantity: Decimal
    limit_price: Decimal
    fee_bps: Decimal
    timestamp: int

    def __post_init__(self) -> None:
        validate_id(self.order_id)
        validate_id(self.product_id)
        validate_timestamp(self.timestamp)
        if self.side not in ("BUY", "SELL"):
            raise ValueError("only BUY and SELL spot intents are supported")
        _positive_fields(self, ("quantity", "limit_price"))
        _positive_fields(self, ("fee_bps",), allow_zero=True)
        if self.fee_bps >= 10000:
            raise ValueError("fee assumption must be less than 100%")


@dataclass(frozen=True)
class Fill:
    fill_id: str
    order_id: str
    product_id: str
    side: str
    quantity: Decimal
    price: Decimal
    fee_quote: Decimal
    timestamp: int

    def __post_init__(self) -> None:
        validate_id(self.fill_id)
        validate_id(self.order_id)
        validate_id(self.product_id)
        validate_timestamp(self.timestamp)
        if self.side not in ("BUY", "SELL"):
            raise ValueError("invalid spot fill side")
        _positive_fields(self, ("quantity", "price"))
        _positive_fields(self, ("fee_quote",), allow_zero=True)
