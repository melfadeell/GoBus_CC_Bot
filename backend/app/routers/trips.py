from datetime import date as date_cls, time as time_cls

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_admin
from app.database import get_db
from app.models.models import AdminUser, Route, Trip
from app.schemas.schemas import PaginatedResponse, RouteOut, TripCreate, TripOut, TripUpdate

router = APIRouter(prefix="/api/trips", tags=["trips"])

_TRIP_LOADS = (
    joinedload(Trip.route),
    joinedload(Trip.departure_station),
    joinedload(Trip.arrival_station),
)


@router.get("/routes", response_model=list[RouteOut])
def list_routes(db: Session = Depends(get_db), _: AdminUser = Depends(get_current_admin)):
    return db.query(Route).filter(Route.is_active.is_(True)).order_by(Route.origin).all()


def _parse_time(value: str | None) -> time_cls | None:
    if not value:
        return None
    try:
        parts = value.split(":")
        return time_cls(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
    except (ValueError, IndexError):
        return None


@router.get("", response_model=PaginatedResponse[TripOut])
def list_trips(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    route_id: int | None = None,
    status: str | None = None,
    date_from: date_cls | None = None,
    date_to: date_cls | None = None,
    departure_station_id: int | None = None,
    departure_from: str | None = None,
    departure_to: str | None = None,
    bus_class: str | None = None,
    price_min: float | None = None,
    price_max: float | None = None,
    is_bookable: bool | None = None,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    q = db.query(Trip).options(*_TRIP_LOADS)
    if route_id:
        q = q.filter(Trip.route_id == route_id)
    if status:
        q = q.filter(Trip.status == status)
    if date_from:
        q = q.filter(Trip.trip_date >= date_from)
    if date_to:
        q = q.filter(Trip.trip_date <= date_to)
    if departure_station_id:
        q = q.filter(Trip.departure_station_id == departure_station_id)
    dep_from = _parse_time(departure_from)
    dep_to = _parse_time(departure_to)
    if dep_from:
        q = q.filter(Trip.departure_time >= dep_from)
    if dep_to:
        q = q.filter(Trip.departure_time <= dep_to)
    if bus_class:
        q = q.filter(Trip.bus_class == bus_class)
    if price_min is not None:
        q = q.filter(Trip.price_egp >= price_min)
    if price_max is not None:
        q = q.filter(Trip.price_egp <= price_max)
    if is_bookable is not None:
        q = q.filter(Trip.is_bookable.is_(is_bookable))
    total = q.count()
    items = (
        q.order_by(Trip.trip_date.desc(), Trip.departure_time)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{trip_id}", response_model=TripOut)
def get_trip(trip_id: int, db: Session = Depends(get_db), _: AdminUser = Depends(get_current_admin)):
    trip = db.query(Trip).options(*_TRIP_LOADS).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


@router.post("", response_model=TripOut)
def create_trip(
    payload: TripCreate, db: Session = Depends(get_db), _: AdminUser = Depends(get_current_admin)
):
    trip = Trip(**payload.model_dump())
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


@router.put("/{trip_id}", response_model=TripOut)
def update_trip(
    trip_id: int,
    payload: TripUpdate,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    trip = db.query(Trip).options(*_TRIP_LOADS).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(trip, key, value)
    db.commit()
    db.refresh(trip)
    return trip


@router.delete("/{trip_id}")
def delete_trip(trip_id: int, db: Session = Depends(get_db), _: AdminUser = Depends(get_current_admin)):
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    db.delete(trip)
    db.commit()
    return {"ok": True}
