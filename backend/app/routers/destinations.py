from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.services import reference_cache
from app.database import get_db
from app.models.models import AdminUser, Destination
from app.schemas.schemas import DestinationCreate, DestinationOut, DestinationUpdate, PaginatedResponse
from app.utils.text_utils import unique_slug

router = APIRouter(prefix="/api/destinations", tags=["destinations"])


@router.get("", response_model=PaginatedResponse[DestinationOut])
def list_destinations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    q = db.query(Destination)
    if search:
        q = q.filter(Destination.name_ar.contains(search) | Destination.content.contains(search))
    total = q.count()
    items = q.order_by(Destination.name_ar).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{dest_id}", response_model=DestinationOut)
def get_destination(dest_id: int, db: Session = Depends(get_db), _: AdminUser = Depends(get_current_admin)):
    dest = db.query(Destination).filter(Destination.id == dest_id).first()
    if not dest:
        raise HTTPException(status_code=404, detail="Destination not found")
    return dest


@router.post("", response_model=DestinationOut)
def create_destination(
    payload: DestinationCreate, db: Session = Depends(get_db), _: AdminUser = Depends(get_current_admin)
):
    data = payload.model_dump()
    slug = data.get("slug") or unique_slug(
        data["name_ar"],
        {row[0] for row in db.query(Destination.slug).all()},
    )
    data["slug"] = slug
    dest = Destination(**data)
    db.add(dest)
    db.commit()
    reference_cache.invalidate()
    db.refresh(dest)
    return dest


@router.put("/{dest_id}", response_model=DestinationOut)
def update_destination(
    dest_id: int,
    payload: DestinationUpdate,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    dest = db.query(Destination).filter(Destination.id == dest_id).first()
    if not dest:
        raise HTTPException(status_code=404, detail="Destination not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(dest, key, value)
    db.commit()
    reference_cache.invalidate()
    db.refresh(dest)
    return dest


@router.delete("/{dest_id}")
def delete_destination(
    dest_id: int, db: Session = Depends(get_db), _: AdminUser = Depends(get_current_admin)
):
    dest = db.query(Destination).filter(Destination.id == dest_id).first()
    if not dest:
        raise HTTPException(status_code=404, detail="Destination not found")
    db.delete(dest)
    db.commit()
    reference_cache.invalidate()
    return {"ok": True}
