import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .keitaro import KeitaroClient, KeitaroError
from .models import CampaignStream, OfferBinding, OperationLog
from .schemas import CampaignCreate
from .weights import WeightError, redistribute, validate_publish


def write_log(db: Session, action: str, *, campaign_id: int | None = None,
              stream_id: int | None = None, status: str = "success", details: str = "") -> None:
    db.add(OperationLog(campaign_id=campaign_id, stream_id=stream_id, action=action,
                        status=status, details=details[:2000]))
    db.commit()


def campaign_streams(db: Session, campaign_id: int) -> list[CampaignStream]:
    return list(db.scalars(select(CampaignStream).where(
        CampaignStream.campaign_id == campaign_id).order_by(CampaignStream.position, CampaignStream.stream_id)))


def stream_bindings(db: Session, stream_id: int) -> list[OfferBinding]:
    return list(db.scalars(select(OfferBinding).where(
        OfferBinding.stream_id == stream_id).order_by(OfferBinding.offer_id)))


def has_draft(bindings: list[OfferBinding]) -> bool:
    return any(
        item.present != item.baseline_present
        or item.share != item.baseline_share
        or item.pinned != item.baseline_pinned
        for item in bindings
    )


def binding_dict(item: OfferBinding) -> dict[str, Any]:
    dirty = (item.present != item.baseline_present or item.share != item.baseline_share
             or item.pinned != item.baseline_pinned)
    if not item.present:
        state = "removed"
    elif not item.baseline_present:
        state = "added" if dirty else "active"
    else:
        state = "modified" if dirty else "active"
    return {
        "offer_id": item.offer_id,
        "offer_name": item.offer_name,
        "share": item.share if item.present else 0,
        "pinned": item.pinned if item.present else False,
        "present": item.present,
        "state": state,
        "dirty": dirty,
    }


def stream_dict(db: Session, stream: CampaignStream) -> dict[str, Any]:
    rows = stream_bindings(db, stream.stream_id)
    dirty = has_draft(rows)
    return {
        "stream_id": stream.stream_id,
        "campaign_id": stream.campaign_id,
        "name": stream.name,
        "position": stream.position,
        "offers": [binding_dict(row) for row in rows],
        "dirty": dirty,
        "has_offer_flow": stream.managed_offer_flow,
    }


def redistribute_stream(db: Session, stream_id: int) -> list[OfferBinding]:
    rows = stream_bindings(db, stream_id)
    redistribute(rows)
    db.commit()
    return rows


def create_campaign(db: Session, client: KeitaroClient, payload: CampaignCreate) -> dict:
    countries = list(dict.fromkeys(code.strip().upper() for code in payload.country_codes if code.strip()))
    if not countries:
        raise ValueError("Выберите хотя бы одну страну.")
    if any(not re.fullmatch(r"[A-Z]{2}", code) for code in countries):
        raise ValueError("Коды стран должны состоять из двух букв, например AU.")

    catalogs = client.get_catalogs()
    offer = next((item for item in catalogs["offers"] if int(item.get("id", -1)) == payload.offer_id), None)
    if offer is None:
        raise ValueError("Выбранный оффер не найден в каталоге Keitaro.")
    if not any(int(item.get("id", -1)) == payload.domain_id for item in catalogs["domains"]):
        raise ValueError("Выбранный домен отсутствует в каталоге Keitaro.")
    if not any(int(item.get("id", -1)) == payload.group_id for item in catalogs["groups"]):
        raise ValueError("Выбранная группа отсутствует в каталоге Keitaro.")
    if not any(int(item.get("id", -1)) == payload.traffic_source_id for item in catalogs["traffic_sources"]):
        raise ValueError("Выбранный источник отсутствует в каталоге Keitaro.")

    prefix = settings.campaign_prefix.strip()
    name = payload.name.strip()
    if not name:
        raise ValueError("Название кампании не должно быть пустым.")
    full_name = name if name.lower().startswith(prefix.lower()) else f"{prefix}{name}"
    campaign = client.create_campaign({
        "name": full_name,
        "state": "disabled",
        "domain_id": payload.domain_id,
        "group_id": payload.group_id,
        "traffic_source_id": payload.traffic_source_id,
    })
    campaign_id = int(campaign["id"])
    write_log(db, "campaign.create", campaign_id=campaign_id, details=f"Создана выключенная кампания «{full_name}».")

    try:
        geo_stream = client.create_stream({
            "campaign_id": campaign_id,
            "name": "Flow 1 — GEO → Google",
            "type": "regular",
            "schema": "redirect",
            "action_type": "http",
            "action_payload": "https://google.com",
            "filters": [{"name": "country", "mode": "accept", "payload": countries}],
        })
    except KeitaroError as exc:
        write_log(db, "stream.create.geo", campaign_id=campaign_id, status="error", details=str(exc))
        raise
    geo_id = int(geo_stream["id"])
    db.add(CampaignStream(stream_id=geo_id, campaign_id=campaign_id,
                          name=geo_stream.get("name", "Flow 1 — GEO → Google"),
                          position=int(geo_stream.get("position", 1)), managed_offer_flow=False))
    write_log(db, "stream.create.geo", campaign_id=campaign_id, stream_id=geo_id,
              details=f"Гео-поток создан для стран: {', '.join(countries)}.")

    try:
        offer_stream = client.create_stream({
            "campaign_id": campaign_id,
            "name": "Flow 2 — Offers",
            "type": "default",
            "schema": "landings",
            "offers": [{"offer_id": payload.offer_id, "share": 100, "state": "active"}],
        })
    except KeitaroError as exc:
        write_log(db, "stream.create.offers", campaign_id=campaign_id, status="error", details=str(exc))
        raise
    offer_stream_id = int(offer_stream["id"])
    offer_stream_name = offer_stream.get("name", "Flow 2 — Offers")
    db.add(CampaignStream(stream_id=offer_stream_id, campaign_id=campaign_id,
                          name=offer_stream_name, position=int(offer_stream.get("position", 2)),
                          managed_offer_flow=True))
    db.add(OfferBinding(
        campaign_id=campaign_id, stream_id=offer_stream_id, stream_name=offer_stream_name,
        offer_id=payload.offer_id, offer_name=offer.get("name", f"Offer {payload.offer_id}"),
        ever_synced=True,
        baseline_present=True, present=True, baseline_share=100, share=100,
        baseline_pinned=False, pinned=False,
    ))
    write_log(db, "stream.create.offers", campaign_id=campaign_id, stream_id=offer_stream_id,
              details=f"Поток создан с оффером {payload.offer_id} (100%).")

    try:
        remote_order = client.get_streams(campaign_id)
        if [int(item["id"]) for item in remote_order[:2]] != [geo_id, offer_stream_id]:
            raise KeitaroError("Keitaro изменил порядок потоков; кампания оставлена выключенной.", 502)
        client.enable_campaign(campaign_id)
    except KeitaroError as exc:
        write_log(db, "campaign.enable", campaign_id=campaign_id, status="error", details=str(exc))
        raise
    write_log(db, "campaign.enable", campaign_id=campaign_id, details="Кампания включена после настройки потоков.")
    return {**campaign, "id": campaign_id, "name": full_name, "state": "active",
            "streams": [geo_id, offer_stream_id]}


def fetch_campaign_streams(db: Session, client: KeitaroClient, campaign_id: int) -> list[dict]:
    streams = client.get_streams(campaign_id)
    catalog_offers = client.request("GET", "/offers")
    names = {int(item["id"]): item.get("name", f"Offer {item['id']}") for item in catalog_offers}
    for position, summary in enumerate(streams, start=1):
        stream_id = int(summary["id"])
        # The campaign endpoint normally includes nested offers. Fetch one stream only
        # when that field is absent; filters/actions for offerless flows are not parsed.
        detail = summary if "offers" in summary else client.get_stream(stream_id)
        offers = detail.get("offers") or []
        if "offers" not in summary and not offers:
            detail = summary
        name = str(detail.get("name") or summary.get("name") or f"Flow {position}")
        row = db.get(CampaignStream, stream_id)
        if row is None:
            row = CampaignStream(stream_id=stream_id, campaign_id=campaign_id, name=name,
                                 position=int(summary.get("position", position)),
                                 managed_offer_flow=bool(offers))
            db.add(row)
        else:
            row.name = name
            row.position = int(summary.get("position", position))
            row.managed_offer_flow = row.managed_offer_flow or bool(offers)

        for remote in offers:
            offer_id = int(remote["offer_id"])
            binding = db.scalar(select(OfferBinding).where(
                OfferBinding.stream_id == stream_id, OfferBinding.offer_id == offer_id))
            share = int(remote.get("share", 0))
            if binding is None:
                db.add(OfferBinding(
                    campaign_id=campaign_id, stream_id=stream_id, stream_name=name,
                    offer_id=offer_id, offer_name=names.get(offer_id, f"Offer {offer_id}"),
                    ever_synced=True,
                    baseline_present=True, present=True, baseline_share=share, share=share,
                    baseline_pinned=False, pinned=False,
                ))
            else:
                binding.campaign_id = campaign_id
                binding.stream_name = name
                binding.offer_name = names.get(offer_id, binding.offer_name or f"Offer {offer_id}")
                binding.ever_synced = True
                binding.baseline_present = True
                binding.present = True
                binding.baseline_share = share
                binding.share = share
                binding.baseline_pinned = binding.pinned
                binding.pinned = binding.pinned

        known = stream_bindings(db, stream_id)
        current_offer_ids = {int(item["offer_id"]) for item in offers}
        for binding in known:
            if binding.offer_id not in current_offer_ids and binding.baseline_present:
                binding.baseline_present = False
                binding.present = False
                binding.baseline_share = 0
                binding.share = 0
                binding.baseline_pinned = False
                binding.pinned = False
                binding.offer_name = names.get(binding.offer_id, binding.offer_name)

    db.commit()
    write_log(db, "streams.fetch", campaign_id=campaign_id,
              details=f"Синхронизировано потоков: {len(streams)}; удалённые связи сохранены в архиве.")
    return [stream_dict(db, item) for item in campaign_streams(db, campaign_id)]


def add_offer(db: Session, client: KeitaroClient, campaign_id: int, stream_id: int, offer_id: int) -> None:
    catalogs = client.request("GET", "/offers")
    offer = next((item for item in catalogs if int(item.get("id", -1)) == offer_id), None)
    if offer is None:
        raise ValueError("Оффер не найден в каталоге Keitaro.")
    existing = db.scalar(select(OfferBinding).where(
        OfferBinding.stream_id == stream_id, OfferBinding.offer_id == offer_id))
    if existing and existing.present:
        raise ValueError("Этот оффер уже есть в потоке.")
    rows = stream_bindings(db, stream_id)
    if existing is None:
        existing = OfferBinding(
            campaign_id=campaign_id, stream_id=stream_id,
            stream_name=db.get(CampaignStream, stream_id).name,
            offer_id=offer_id, offer_name=offer.get("name", f"Offer {offer_id}"),
            baseline_present=False, present=True, baseline_share=0, share=0,
            baseline_pinned=False, pinned=False,
        )
        db.add(existing)
        rows.append(existing)
    else:
        existing.present = True
        existing.share = 0
        existing.pinned = False
        rows.append(existing)
    redistribute(rows)
    db.commit()
    write_log(db, "offer.add.draft", campaign_id=campaign_id, stream_id=stream_id,
              details=f"Оффер {offer_id} добавлен в локальный черновик.")


def remove_offer(db: Session, campaign_id: int, stream_id: int, offer_id: int) -> None:
    binding = db.scalar(select(OfferBinding).where(
        OfferBinding.stream_id == stream_id, OfferBinding.offer_id == offer_id))
    if binding is None or not binding.present:
        raise ValueError("Активный оффер не найден в потоке.")
    rows = stream_bindings(db, stream_id)
    free_after = [row for row in rows if row.present and not row.pinned and row.offer_id != offer_id]
    if not binding.pinned and not free_after:
        raise ValueError("Нельзя удалить последний свободный оффер. Снимите pin с другого оффера или добавьте замену.")
    was_pinned = binding.pinned
    if not binding.baseline_present:
        db.delete(binding)
        remaining = [row for row in rows if row is not binding]
    else:
        binding.present = False
        binding.share = 0
        binding.pinned = False
        remaining = rows
    redistribute(remaining)
    db.commit()
    write_log(db, "offer.remove.draft", campaign_id=campaign_id, stream_id=stream_id,
              details=f"Оффер {offer_id} помечен удалённым в черновике; pin снят ({was_pinned}).")


def restore_offer(db: Session, campaign_id: int, stream_id: int, offer_id: int) -> None:
    binding = db.scalar(select(OfferBinding).where(
        OfferBinding.stream_id == stream_id, OfferBinding.offer_id == offer_id))
    if binding is None or binding.present:
        raise ValueError("Архивный оффер не найден.")
    binding.present = True
    binding.share = 0
    binding.pinned = False
    redistribute(stream_bindings(db, stream_id))
    db.commit()
    write_log(db, "offer.restore.draft", campaign_id=campaign_id, stream_id=stream_id,
              details=f"Оффер {offer_id} возвращён в черновик без pin.")


def purge_archived_offer(db: Session, campaign_id: int, stream_id: int, offer_id: int) -> None:
    binding = db.scalar(select(OfferBinding).where(
        OfferBinding.campaign_id == campaign_id,
        OfferBinding.stream_id == stream_id,
        OfferBinding.offer_id == offer_id,
    ))
    if binding is None or binding.present:
        raise ValueError("Окончательно удалить можно только оффер из архива.")
    db.delete(binding)
    db.commit()
    write_log(db, "offer.archive.purged", campaign_id=campaign_id, stream_id=stream_id,
              details=f"Архивная связь оффера {offer_id} окончательно удалена из локальной базы.")


def toggle_pin(db: Session, campaign_id: int, stream_id: int, offer_id: int) -> None:
    binding = db.scalar(select(OfferBinding).where(
        OfferBinding.stream_id == stream_id, OfferBinding.offer_id == offer_id))
    if binding is None or not binding.present:
        raise ValueError("Активный оффер не найден.")
    rows = stream_bindings(db, stream_id)
    if not binding.pinned and sum(1 for row in rows if row.present and not row.pinned) <= 1:
        raise ValueError("Нельзя закрепить последний свободный оффер.")
    binding.pinned = not binding.pinned
    redistribute(rows)
    db.commit()
    write_log(db, "offer.pin", campaign_id=campaign_id, stream_id=stream_id,
              details=f"Для оффера {offer_id} pin {'включён' if binding.pinned else 'снят'}.")


def set_pinned_share(db: Session, campaign_id: int, stream_id: int, offer_id: int, share: int) -> None:
    binding = db.scalar(select(OfferBinding).where(
        OfferBinding.campaign_id == campaign_id,
        OfferBinding.stream_id == stream_id,
        OfferBinding.offer_id == offer_id,
    ))
    if binding is None or not binding.present or not binding.pinned:
        raise ValueError("Вручную менять долю можно только у активного закреплённого оффера.")
    rows = stream_bindings(db, stream_id)
    free = [row for row in rows if row.present and not row.pinned]
    if not free:
        raise ValueError("Оставьте хотя бы один активный оффер без pin.")
    pinned_total = sum(row.share for row in rows if row.present and row.pinned and row is not binding)
    if pinned_total + share > 100:
        raise ValueError(f"Сумма закреплённых долей не может превышать 100% (сейчас закреплено {pinned_total}%).")

    binding.share = share
    redistribute(rows)
    db.commit()
    write_log(db, "offer.share", campaign_id=campaign_id, stream_id=stream_id,
              details=f"Закреплённая доля оффера {offer_id} установлена на {share}%; остальные доли пересчитаны.")


def publish_stream(db: Session, client: KeitaroClient, campaign_id: int, stream_id: int) -> list[dict]:
    rows = stream_bindings(db, stream_id)
    active = validate_publish(rows)
    payload = {"offers": [{"offer_id": row.offer_id, "share": row.share, "state": "active"}
                          for row in active]}
    client.update_stream(stream_id, payload)
    verified = client.get_stream(stream_id)
    remote = {int(item["offer_id"]): int(item.get("share", 0)) for item in verified.get("offers", [])}
    if remote != {row.offer_id: row.share for row in active}:
        write_log(db, "stream.push", campaign_id=campaign_id, stream_id=stream_id, status="error",
                  details="Ответ Keitaro не совпал с опубликованным черновиком; требуется повторная Fetch.")
        raise KeitaroError("После публикации состав потока в Keitaro не совпал с черновиком.", 502)

    for row in rows:
        row.baseline_present = row.present
        row.baseline_share = row.share if row.present else 0
        row.baseline_pinned = row.pinned if row.present else False
        row.ever_synced = row.ever_synced or row.present
        row.pinned = row.pinned if row.present else False
    db.commit()
    write_log(db, "stream.push", campaign_id=campaign_id, stream_id=stream_id,
              details=f"Опубликовано активных офферов: {len(active)}.")
    return [binding_dict(row) for row in stream_bindings(db, stream_id)]


def cancel_stream(db: Session, campaign_id: int, stream_id: int) -> list[dict]:
    rows = stream_bindings(db, stream_id)
    for row in rows:
        if not row.baseline_present:
            if row.ever_synced:
                row.present = False
                row.share = 0
                row.pinned = False
            else:
                db.delete(row)
            continue
        row.present = row.baseline_present
        row.share = row.baseline_share
        row.pinned = row.baseline_pinned
    db.commit()
    write_log(db, "stream.cancel", campaign_id=campaign_id, stream_id=stream_id,
              details="Локальный черновик отменён; архивные связи сохранены, запрос к Keitaro не отправлялся.")
    return [binding_dict(row) for row in stream_bindings(db, stream_id)]
