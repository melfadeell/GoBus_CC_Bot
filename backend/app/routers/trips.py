from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_admin
from app.database import get_db
from app.models.models import AdminUser, Route, Trip
from app.schemas.schemas import PaginatedResponse, RouteOut, TripCreate, TripOut, TripUpdate

router = APIRouter(prefix="/api/trips", tags=["trips"])


@router.get("/routes", response_model=list[RouteOut])
def list_routes(db: Session = Depends(get_db), _: AdminUser = Depends(get_current_admin)):
    return db.query(Route).filter(Route.is_active.is_(True)).order_by(Route.origin).all()


@router.get("", response_model=PaginatedResponse[TripOut])
def list_trips(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    route_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    q = db.query(Trip).options(joinedload(Trip.route))
    if route_id:
        q = q.filter(Trip.route_id == route_id)
    if status:
        q = q.filter(Trip.status == status)
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
    trip = db.query(Trip).options(joinedload(Trip.route)).filter(Trip.id == trip_id).first()
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
    trip = db.query(Trip).options(joinedload(Trip.route)).filter(Trip.id == trip_id).first()
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
