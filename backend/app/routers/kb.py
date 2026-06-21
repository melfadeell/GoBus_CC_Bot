from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_admin
from app.database import get_db
from app.models.models import AdminUser, KbArticle, KbCategory
from app.schemas.schemas import (
    KbArticleCreate,
    KbArticleOut,
    KbArticleUpdate,
    KbCategoryOut,
    PaginatedResponse,
    TextEnhanceRequest,
    TextEnhanceResponse,
)
from app.services.text_enhance import enhance_text
from app.services.file_extract import extract_text_from_upload
from app.utils.text_utils import unique_slug

router = APIRouter(prefix="/api/kb", tags=["kb"])


@router.get("/categories", response_model=list[KbCategoryOut])
def list_categories(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    return db.query(KbCategory).order_by(KbCategory.id).all()


@router.get("", response_model=PaginatedResponse[KbArticleOut])
def list_articles(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    category_id: int | None = None,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    q = db.query(KbArticle).options(joinedload(KbArticle.category))
    if search:
        q = q.filter(KbArticle.title.contains(search) | KbArticle.content.contains(search))
    if category_id:
        q = q.filter(KbArticle.category_id == category_id)
    total = q.count()
    items = q.order_by(KbArticle.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/extract-file", response_model=TextEnhanceResponse)
async def extract_kb_file(
    file: UploadFile = File(...),
    _: AdminUser = Depends(get_current_admin),
):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        text = extract_text_from_upload(data, file.filename or "upload", file.content_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Could not extract text from file") from exc
    if not text.strip():
        raise HTTPException(status_code=422, detail="No readable text found in file")
    return TextEnhanceResponse(text=text.strip())


@router.get("/{article_id}", response_model=KbArticleOut)
def get_article(article_id: int, db: Session = Depends(get_db), _: AdminUser = Depends(get_current_admin)):
    article = (
        db.query(KbArticle)
        .options(joinedload(KbArticle.category))
        .filter(KbArticle.id == article_id)
        .first()
    )
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


@router.post("", response_model=KbArticleOut)
def create_article(
    payload: KbArticleCreate, db: Session = Depends(get_db), _: AdminUser = Depends(get_current_admin)
):
    data = payload.model_dump()
    slug = data.get("slug") or unique_slug(
        data["title"],
        {row[0] for row in db.query(KbArticle.slug).all()},
    )
    if db.query(KbArticle).filter(KbArticle.slug == slug).first():
        raise HTTPException(status_code=400, detail="Slug already exists")
    data["slug"] = slug
    article = KbArticle(**data)
    db.add(article)
    db.commit()
    db.refresh(article)
    return article


@router.put("/{article_id}", response_model=KbArticleOut)
def update_article(
    article_id: int,
    payload: KbArticleUpdate,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    article = db.query(KbArticle).filter(KbArticle.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(article, key, value)
    db.commit()
    db.refresh(article)
    return article


@router.delete("/{article_id}")
def delete_article(
    article_id: int, db: Session = Depends(get_db), _: AdminUser = Depends(get_current_admin)
):
    article = db.query(KbArticle).filter(KbArticle.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    db.delete(article)
    db.commit()
    return {"ok": True}


@router.post("/enhance", response_model=TextEnhanceResponse)
async def enhance_kb_text(
    payload: TextEnhanceRequest,
    _: AdminUser = Depends(get_current_admin),
):
    enhanced = await enhance_text(payload.text)
    return TextEnhanceResponse(text=enhanced)
