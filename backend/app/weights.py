from collections.abc import Iterable

from .models import OfferBinding


class WeightError(ValueError):
    pass


def redistribute(bindings: Iterable[OfferBinding]) -> None:
    bindings = list(bindings)
    active = [item for item in bindings if item.present]
    if not active:
        raise WeightError("В потоке должен остаться хотя бы один активный оффер.")
    free = [item for item in active if not item.pinned]
    if not free:
        raise WeightError("Оставьте хотя бы один активный оффер без pin.")
    pinned_total = sum(item.share for item in active if item.pinned)
    remainder = 100 - pinned_total
    if remainder < 0:
        raise WeightError("Закреплённые доли превышают 100%.")

    each, extra = divmod(remainder, len(free))
    # Stable remainder allocation follows persisted/display order (offer ID).
    for index, item in enumerate(sorted(free, key=lambda value: value.offer_id)):
        item.share = each + (1 if index < extra else 0)
    for item in bindings:
        if not item.present:
            item.share = 0


def validate_publish(bindings: Iterable[OfferBinding]) -> list[OfferBinding]:
    active = [item for item in bindings if item.present]
    if not active:
        raise WeightError("Нельзя опубликовать поток без активных офферов.")
    if not any(not item.pinned for item in active):
        raise WeightError("Оставьте хотя бы один активный оффер без pin.")
    if sum(item.share for item in active) != 100:
        raise WeightError("Сумма долей активных офферов должна быть 100%.")
    if any(item.share < 0 for item in active):
        raise WeightError("Доля оффера не может быть отрицательной.")
    return active
