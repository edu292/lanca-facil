import calendar
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from db import Unit

UNIT_TO_LABEL: dict[Unit, str] = {Unit.UNIT: "unidade", Unit.KG: "kg"}
LABEL_TO_UNIT: dict[str, Unit] = {v: k for k, v in UNIT_TO_LABEL.items()}


def month_label(month: int) -> str:
    return f"{month:02d} - {calendar.month_name[month].capitalize()}"


def month_choices() -> list[str]:
    return [month_label(m) for m in range(1, 13)]


def parse_month_choice(label: str) -> int:
    return int(label.split(" - ", 1)[0])


def parse_decimal(raw: str, label: str = "Valor") -> Decimal:
    try:
        val = Decimal(raw.strip().replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError(f"{label} inválido.") from exc
    if not val.is_finite() or val <= 0:
        raise ValueError(f"{label} deve ser maior que zero.")
    return val


def parse_money(raw: str) -> Decimal:
    return parse_decimal(raw, "Preço").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def parse_quantity(raw: str, unit: Unit) -> Decimal:
    val = parse_decimal(raw, "Quantidade")
    if unit is Unit.UNIT:
        if val != val.to_integral_value():
            raise ValueError(
                "Produtos em 'unidade' não permitem quantidade fracionada."
            )
        return val.to_integral_value()
    return val.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def parse_datetime_br(raw: str) -> datetime:
    text = raw.strip()
    if not text:
        return datetime.now().replace(second=0, microsecond=0)
    try:
        return datetime.strptime(text, "%d/%m/%Y %H:%M")
    except ValueError as exc:
        raise ValueError("Data/hora inválida. Use DD/MM/AAAA HH:MM.") from exc


def fmt_datetime_br(dt: datetime) -> str:
    return dt.strftime("%d/%m/%Y %H:%M")


def fmt_money(amount: Decimal) -> str:
    return f"{amount:.2f}"


def fmt_quantity(qty: Decimal, unit: Unit) -> str:
    return f"{int(qty)}" if unit is Unit.UNIT else f"{qty:.3f}"
