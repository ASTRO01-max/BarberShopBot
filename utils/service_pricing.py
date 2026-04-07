from dataclasses import dataclass
from decimal import Decimal

from utils.discounts import format_discount_percent

SERVICE_DISCOUNT_PERCENT_ATTR = "_service_discount_percent"
SERVICE_DISCOUNTED_PRICE_ATTR = "_service_discounted_price"


@dataclass(frozen=True, slots=True)
class ServicePriceSnapshot:
    base_price: int
    current_price: int
    discount_percent: Decimal | None = None

    @property
    def has_discount(self) -> bool:
        return self.discount_percent is not None


def format_price(price: int | None) -> str:
    normalized_price = int(price or 0)
    return f"{normalized_price:,}".replace(",", " ")


def attach_service_discount_snapshot(
    service: object,
    *,
    discount_percent: Decimal | None,
    discounted_price: int | None,
) -> None:
    setattr(service, SERVICE_DISCOUNT_PERCENT_ATTR, discount_percent)
    setattr(service, SERVICE_DISCOUNTED_PRICE_ATTR, discounted_price)


def get_service_price_snapshot(service: object) -> ServicePriceSnapshot:
    base_price = int(getattr(service, "price", 0) or 0)
    discount_percent = getattr(service, SERVICE_DISCOUNT_PERCENT_ATTR, None)
    discounted_price = getattr(service, SERVICE_DISCOUNTED_PRICE_ATTR, None)

    if discount_percent is None or discounted_price is None:
        return ServicePriceSnapshot(
            base_price=base_price,
            current_price=base_price,
        )

    return ServicePriceSnapshot(
        base_price=base_price,
        current_price=int(discounted_price),
        discount_percent=discount_percent,
    )


def build_service_price_lines(service: object) -> tuple[str, ...]:
    snapshot = get_service_price_snapshot(service)
    if not snapshot.has_discount:
        return (f"💵 <b>Narx:</b> {format_price(snapshot.base_price)} so'm",)

    percent_text = format_discount_percent(snapshot.discount_percent)
    return (
        f"💵 <b>Asl narx:</b> {format_price(snapshot.base_price)} so'm",
        f"🏷 <b>Chegirma:</b> {percent_text}%",
        f"💸 <b>Chegirmali narx:</b> {format_price(snapshot.current_price)} so'm",
    )
