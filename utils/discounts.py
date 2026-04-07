from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from utils.validators import INT32_MAX

PERCENT_MIN = Decimal("0")
PERCENT_MAX = Decimal("100")
PERCENT_SCALE = Decimal("0.01")
MONEY_SCALE = Decimal("1")


class DiscountValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DiscountResult:
    old_price: int
    discount_percent: Decimal
    new_price: int


@dataclass(frozen=True, slots=True)
class BulkDiscountResult:
    item_id: int
    old_price: int
    discount_percent: Decimal
    new_price: int


def _normalize_price(price: int) -> int:
    if not isinstance(price, int):
        raise DiscountValidationError("Narx butun son bo'lishi kerak.")
    if price < 0:
        raise DiscountValidationError("Narx manfiy bo'lishi mumkin emas.")
    if price > INT32_MAX:
        raise DiscountValidationError("Narx ruxsat etilgan chegaradan katta.")
    return price


def _to_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value

    if isinstance(value, str):
        normalized = value.strip().replace(",", ".")
        if not normalized:
            raise DiscountValidationError("Chegirma foizini kiriting.")
        try:
            return Decimal(normalized)
        except InvalidOperation as exc:
            raise DiscountValidationError(
                "Chegirma foizi faqat raqam bo'lishi kerak."
            ) from exc

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise DiscountValidationError(
            "Chegirma foizi faqat raqam bo'lishi kerak."
        ) from exc


def validate_discount_percent(value: object) -> Decimal:
    return normalize_discount_percent(value)


def normalize_discount_percent(value: object) -> Decimal:
    percent = _to_decimal(value)

    if percent <= PERCENT_MIN:
        raise DiscountValidationError("Chegirma foizi 0 dan katta bo'lishi kerak.")
    if percent > PERCENT_MAX:
        raise DiscountValidationError("Chegirma foizi 100% dan oshmasligi kerak.")

    quantized = percent.quantize(PERCENT_SCALE)
    if quantized != percent:
        raise DiscountValidationError(
            "Chegirma foizida ko'pi bilan 2 xonali kasr bo'lishi mumkin."
        )

    return quantized.normalize()


def calculate_discounted_price(price: int, discount_percent: object) -> int:
    normalized_price = _normalize_price(price)
    percent = normalize_discount_percent(discount_percent)

    discounted_price = (
        Decimal(normalized_price)
        * (PERCENT_MAX - percent)
        / PERCENT_MAX
    ).quantize(MONEY_SCALE, rounding=ROUND_HALF_UP)

    return int(discounted_price)


def calculate_discount_details(price: int, discount_percent: object) -> DiscountResult:
    percent = normalize_discount_percent(discount_percent)
    normalized_price = _normalize_price(price)
    new_price = calculate_discounted_price(normalized_price, percent)
    return DiscountResult(
        old_price=normalized_price,
        discount_percent=percent,
        new_price=new_price,
    )


def build_bulk_discount_results(
    items: Iterable[tuple[int, int]],
    discount_percent: object,
) -> list[BulkDiscountResult]:
    percent = normalize_discount_percent(discount_percent)
    results: list[BulkDiscountResult] = []

    for item_id, old_price in items:
        normalized_price = _normalize_price(old_price)
        new_price = calculate_discounted_price(normalized_price, percent)
        results.append(
            BulkDiscountResult(
                item_id=int(item_id),
                old_price=normalized_price,
                discount_percent=percent,
                new_price=new_price,
            )
        )

    return results


def format_discount_percent(discount_percent: object) -> str:
    normalized_percent = normalize_discount_percent(discount_percent)
    return format(normalized_percent, "f").rstrip("0").rstrip(".")
