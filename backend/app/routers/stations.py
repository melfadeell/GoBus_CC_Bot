from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.services import reference_cache
from app.database import get_db
from app.models.models import AdminUser, Station
from app.schemas.schemas import PaginatedResponse, StationCreate, StationOut, StationUpdate

router = APIRouter(prefix="/api/stations", tags=["stations"])


@router.get("", response_model=PaginatedResponse[StationOut])
def list_stations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    q = db.query(Station)
    if search:
        q = q.filter(Station.name.contains(search) | Station.description.contains(search))
    total = q.count()
    items = q.order_by(Station.name).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{station_id}", response_model=StationOut)
def get_station(station_id: int, db: Session = Depends(get_db), _: AdminUser = Depends(get_current_admin)):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")
    return station


@router.post("", response_model=StationOut)
def create_station(
    payload: StationCreate, db: Session = Depends(get_db), _: AdminUser = Depends(get_current_admin)
):
    station = Station(**payload.model_dump())
    db.add(station)
    db.commit()
    reference_cache.invalidate()
    db.refresh(station)
    return station


@router.put("/{station_id}", response_model=StationOut)
def update_station(
    station_id: int,
    payload: StationUpdate,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(station, key, value)
    db.commit()
    reference_cache.invalidate()
    db.refresh(station)
    return station


@router.delete("/{station_id}")
def delete_station(
    station_id: int, db: Session = Depends(get_db), _: AdminUser = Depends(get_current_admin)
):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")
    db.delete(station)
    db.commit()
    reference_cache.invalidate()
    return {"ok": True}
