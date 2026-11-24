from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .keitaro import KeitaroClient, KeitaroError
from .models import CampaignStream, OfferBinding, OperationLog
from .schemas import CampaignCreate, OfferMutation, OfferShareMutation
from .services import (
    add_offer,
    cancel_stream,
    campaign_streams,
    create_campaign,
    fetch_campaign_streams,
    has_draft,
    publish_stream,
    purge_archived_offer,
    remove_offer,
    restore_offer,
    set_pinned_share,
    stream_bindings,
    stream_dict,
    toggle_pin,
    write_log,
)
from .weights import WeightError


app = FastAPI(title="Adrobot Keitaro Wrapper", version="1.0.0")


def get_keitaro() -> KeitaroClient:
    return KeitaroClient()


def handle_error(exc: Exception) -> HTTPException:
    if isinstance(exc, WeightError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, KeitaroError):
        return HTTPException(status_code=exc.status_code, detail=str(exc))
    return HTTPException(status_code=500, detail="Внутренняя ошибка приложения.")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/catalogs")
def catalogs(client: KeitaroClient = Depends(get_keitaro)) -> dict:
    try:
        return client.get_catalogs()
    except KeitaroError as exc:
        raise handle_error(exc) from exc


@app.get("/api/campaigns")
def campaigns(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    client: KeitaroClient = Depends(get_keitaro),
) -> dict:
    try:
        items = client.get_campaigns(offset=offset, limit=limit)
        return {"items": items, "offset": offset, "limit": limit, "count": len(items)}
    except KeitaroError as exc:
        raise handle_error(exc) from exc


@app.post("/api/campaigns")
def create_campaign_route(
    payload: CampaignCreate,
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_keitaro),
) -> dict:
    try:
        result = create_campaign(db, client, payload)
        return result
    except (ValueError, KeitaroError, WeightError) as exc:
        raise handle_error(exc) from exc


@app.get("/api/campaigns/{campaign_id}/streams")
def local_streams(campaign_id: int, db: Session = Depends(get_db)) -> list[dict]:
    return [stream_dict(db, item) for item in campaign_streams(db, campaign_id)]


@app.post("/api/campaigns/{campaign_id}/streams/fetch")
def fetch_streams_route(
    campaign_id: int,
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_keitaro),
) -> list[dict]:
    all_rows = list(db.scalars(select(OfferBinding).where(OfferBinding.campaign_id == campaign_id)))
    if any(has_draft([row]) for row in all_rows):
        raise HTTPException(status_code=409, detail="Сначала опубликуйте или отмените локальные изменения.")
    try:
        return fetch_campaign_streams(db, client, campaign_id)
    except KeitaroError as exc:
        write_log(db, "streams.fetch", campaign_id=campaign_id, status="error", details=str(exc))
        raise handle_error(exc) from exc


def ensure_stream(db: Session, campaign_id: int, stream_id: int) -> CampaignStream:
    stream = db.get(CampaignStream, stream_id)
    if stream is None or stream.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="Поток не найден в этой кампании. Нажмите Fetch Streams.")
    return stream


@app.post("/api/campaigns/{campaign_id}/streams/{stream_id}/offers")
def add_offer_route(
    campaign_id: int,
    stream_id: int,
    payload: OfferMutation,
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_keitaro),
) -> dict:
    ensure_stream(db, campaign_id, stream_id)
    try:
        add_offer(db, client, campaign_id, stream_id, payload.offer_id)
        return stream_dict(db, db.get(CampaignStream, stream_id))
    except (ValueError, KeitaroError, WeightError) as exc:
        write_log(db, "offer.add.draft", campaign_id=campaign_id, stream_id=stream_id,
                  status="error", details=str(exc))
        raise handle_error(exc) from exc


@app.post("/api/campaigns/{campaign_id}/streams/{stream_id}/offers/{offer_id}/remove")
def remove_offer_route(campaign_id: int, stream_id: int, offer_id: int,
                       db: Session = Depends(get_db)) -> dict:
    ensure_stream(db, campaign_id, stream_id)
    try:
        remove_offer(db, campaign_id, stream_id, offer_id)
        return stream_dict(db, db.get(CampaignStream, stream_id))
    except (ValueError, WeightError) as exc:
        write_log(db, "offer.remove.draft", campaign_id=campaign_id, stream_id=stream_id,
                  status="error", details=str(exc))
        raise handle_error(exc) from exc


@app.post("/api/campaigns/{campaign_id}/streams/{stream_id}/offers/{offer_id}/restore")
def restore_offer_route(campaign_id: int, stream_id: int, offer_id: int,
                        db: Session = Depends(get_db), client: KeitaroClient = Depends(get_keitaro)) -> dict:
    ensure_stream(db, campaign_id, stream_id)
    try:
        # Confirm that the catalog entry still exists before offering it for restoration.
        catalog = client.request("GET", f"/offers/{offer_id}")
        if not catalog or int(catalog.get("id", -1)) != offer_id:
            raise ValueError("Сам оффер удалён из каталога Keitaro и больше не доступен.")
        restore_offer(db, campaign_id, stream_id, offer_id)
        row = db.scalar(select(OfferBinding).where(OfferBinding.stream_id == stream_id,
                                                 OfferBinding.offer_id == offer_id))
        row.offer_name = catalog.get("name", row.offer_name)
        db.commit()
        return stream_dict(db, db.get(CampaignStream, stream_id))
    except (ValueError, KeitaroError, WeightError) as exc:
        write_log(db, "offer.restore.draft", campaign_id=campaign_id, stream_id=stream_id,
                  status="error", details=str(exc))
        raise handle_error(exc) from exc


@app.delete("/api/campaigns/{campaign_id}/streams/{stream_id}/offers/{offer_id}/archive")
def purge_archived_offer_route(campaign_id: int, stream_id: int, offer_id: int,
                               db: Session = Depends(get_db)) -> dict:
    ensure_stream(db, campaign_id, stream_id)
    try:
        purge_archived_offer(db, campaign_id, stream_id, offer_id)
        return stream_dict(db, db.get(CampaignStream, stream_id))
    except ValueError as exc:
        write_log(db, "offer.archive.purged", campaign_id=campaign_id, stream_id=stream_id,
                  status="error", details=str(exc))
        raise handle_error(exc) from exc


@app.post("/api/campaigns/{campaign_id}/streams/{stream_id}/offers/{offer_id}/pin")
def pin_offer_route(campaign_id: int, stream_id: int, offer_id: int,
                    db: Session = Depends(get_db)) -> dict:
    ensure_stream(db, campaign_id, stream_id)
    try:
        toggle_pin(db, campaign_id, stream_id, offer_id)
        return stream_dict(db, db.get(CampaignStream, stream_id))
    except (ValueError, WeightError) as exc:
        write_log(db, "offer.pin", campaign_id=campaign_id, stream_id=stream_id,
                  status="error", details=str(exc))
        raise handle_error(exc) from exc


@app.put("/api/campaigns/{campaign_id}/streams/{stream_id}/offers/{offer_id}/share")
def set_offer_share_route(campaign_id: int, stream_id: int, offer_id: int,
                          payload: OfferShareMutation,
                          db: Session = Depends(get_db)) -> dict:
    ensure_stream(db, campaign_id, stream_id)
    try:
        set_pinned_share(db, campaign_id, stream_id, offer_id, payload.share)
        return stream_dict(db, db.get(CampaignStream, stream_id))
    except (ValueError, WeightError) as exc:
        write_log(db, "offer.share", campaign_id=campaign_id, stream_id=stream_id,
                  status="error", details=str(exc))
        raise handle_error(exc) from exc


@app.post("/api/campaigns/{campaign_id}/streams/{stream_id}/push")
def push_stream_route(campaign_id: int, stream_id: int,
                      db: Session = Depends(get_db), client: KeitaroClient = Depends(get_keitaro)) -> dict:
    ensure_stream(db, campaign_id, stream_id)
    try:
        publish_stream(db, client, campaign_id, stream_id)
        return stream_dict(db, db.get(CampaignStream, stream_id))
    except (ValueError, KeitaroError, WeightError) as exc:
        write_log(db, "stream.push", campaign_id=campaign_id, stream_id=stream_id,
                  status="error", details=str(exc))
        raise handle_error(exc) from exc


@app.post("/api/campaigns/{campaign_id}/streams/{stream_id}/cancel")
def cancel_stream_route(campaign_id: int, stream_id: int,
                        db: Session = Depends(get_db)) -> dict:
    ensure_stream(db, campaign_id, stream_id)
    cancel_stream(db, campaign_id, stream_id)
    return stream_dict(db, db.get(CampaignStream, stream_id))


@app.get("/api/campaigns/{campaign_id}/history")
def history(campaign_id: int, db: Session = Depends(get_db)) -> list[dict]:
    rows = list(db.scalars(select(OperationLog).where(
        OperationLog.campaign_id == campaign_id).order_by(OperationLog.created_at.desc()).limit(100)))
    return [{"id": row.id, "action": row.action, "status": row.status,
             "details": row.details, "created_at": row.created_at.isoformat()} for row in rows]


@app.get("/api/history")
def all_history(
    campaign_id: int | None = Query(default=None, ge=1),
    action: str | None = Query(default=None, max_length=64),
    status: str | None = Query(default=None, max_length=24),
    search: str | None = Query(default=None, max_length=200),
    date_from: date | None = None,
    date_to: date | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    statement = select(OperationLog)
    if campaign_id is not None:
        statement = statement.where(OperationLog.campaign_id == campaign_id)
    if action:
        statement = statement.where(OperationLog.action.ilike(f"%{action.strip()}%"))
    if status:
        statement = statement.where(OperationLog.status == status)
    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(or_(OperationLog.action.ilike(pattern), OperationLog.details.ilike(pattern)))
    if date_from:
        statement = statement.where(OperationLog.created_at >= datetime.combine(
            date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        end_exclusive = date_to + timedelta(days=1)
        statement = statement.where(OperationLog.created_at < datetime.combine(
            end_exclusive, time.min, tzinfo=timezone.utc))

    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = list(db.scalars(statement.order_by(OperationLog.created_at.desc(), OperationLog.id.desc())
                           .offset(offset).limit(limit + 1)))
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {
        "items": [{"id": row.id, "campaign_id": row.campaign_id, "stream_id": row.stream_id,
                   "action": row.action, "status": row.status, "details": row.details,
                   "created_at": row.created_at.isoformat()} for row in rows],
        "offset": offset,
        "limit": limit,
        "total": total,
        "has_more": has_more,
    }


frontend_dir = Path(settings.frontend_dist)
if frontend_dir.exists():
    assets = frontend_dir / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def frontend(full_path: str):
        candidate = frontend_dir / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        index = frontend_dir / "index.html"
        if index.exists():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="Frontend build not found")
