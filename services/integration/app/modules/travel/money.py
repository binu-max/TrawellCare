from decimal import Decimal, ROUND_HALF_UP

_EXPONENTS = {"OMR": 3, "BHD": 3, "KWD": 3, "JPY": 0}


def minor_exponent(currency: str) -> int:
    return _EXPONENTS.get(currency.upper(), 2)


def to_minor(amount: Decimal | float | int | str, currency: str) -> int:
    exponent = minor_exponent(currency)
    quantum = Decimal(10) ** -exponent
    decimal_amount = Decimal(str(amount)).quantize(quantum, rounding=ROUND_HALF_UP)
    return int(decimal_amount * (Decimal(10) ** exponent))
