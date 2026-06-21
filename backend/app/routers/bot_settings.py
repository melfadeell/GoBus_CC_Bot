from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models.models import AdminUser, BotPromptVersion, BotSettings
from app.schemas.schemas import (
    BotSettingsOut,
    BotSettingsUpdate,
    PromptEnhanceRequest,
    PromptEnhanceResponse,
    PromptSaveRequest,
    PromptVersionOut,
)
from app.services.chat_service import get_bot_settings
from app.services.prompt_enhance import enhance_prompt

router = APIRouter(prefix="/api/bot-settings", tags=["bot-settings"])


def _next_version_number(db: Session) -> int:
    current = db.query(func.max(BotPromptVersion.version_number)).scalar()
    return (current or 0) + 1


def _save_prompt_version(
    db: Session,
    system_prompt: str,
    instruction_note: str | None,
    admin_id: int | None,
) -> BotPromptVersion:
    version = BotPromptVersion(
        version_number=_next_version_number(db),
        system_prompt=system_prompt,
        instruction_note=instruction_note,
        created_by=admin_id,
    )
    db.add(version)
    return version


@router.get("", response_model=BotSettingsOut)
def get_settings(db: Session = Depends(get_db), _: AdminUser = Depends(get_current_admin)):
    bot = get_bot_settings(db)
    return BotSettingsOut(id=bot.id, system_prompt=bot.system_prompt, greeting_ar=bot.greeting_ar)


@router.put("", response_model=BotSettingsOut)
def update_settings(
    payload: BotSettingsUpdate,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    bot = get_bot_settings(db)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(bot, key, value)
    db.commit()
    db.refresh(bot)
    return BotSettingsOut(id=bot.id, system_prompt=bot.system_prompt, greeting_ar=bot.greeting_ar)


@router.get("/prompt-versions", response_model=list[PromptVersionOut])
def list_prompt_versions(db: Session = Depends(get_db), _: AdminUser = Depends(get_current_admin)):
    return (
        db.query(BotPromptVersion)
        .order_by(BotPromptVersion.version_number.desc())
        .limit(50)
        .all()
    )


@router.post("/prompt/enhance", response_model=PromptEnhanceResponse)
async def enhance_system_prompt(
    payload: PromptEnhanceRequest,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
):
    bot = get_bot_settings(db)
    base = payload.base_prompt or bot.system_prompt
    proposed = await enhance_prompt(base, payload.instruction)
    return PromptEnhanceResponse(proposed_prompt=proposed)


@router.put("/prompt", response_model=BotSettingsOut)
def save_system_prompt(
    payload: PromptSaveRequest,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    bot = get_bot_settings(db)
    bot.system_prompt = payload.system_prompt
    _save_prompt_version(db, payload.system_prompt, payload.instruction_note, admin.id)
    db.commit()
    db.refresh(bot)
    return BotSettingsOut(id=bot.id, system_prompt=bot.system_prompt, greeting_ar=bot.greeting_ar)


@router.post("/prompt/restore/{version_id}", response_model=BotSettingsOut)
def restore_prompt_version(
    version_id: int,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    version = db.query(BotPromptVersion).filter(BotPromptVersion.id == version_id).first()
    if not version:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Version not found")

    bot = get_bot_settings(db)
    bot.system_prompt = version.system_prompt
    _save_prompt_version(
        db,
        version.system_prompt,
        f"Restored from version {version.version_number}",
        admin.id,
    )
    db.commit()
    db.refresh(bot)
    return BotSettingsOut(id=bot.id, system_prompt=bot.system_prompt, greeting_ar=bot.greeting_ar)


@router.get("/public/greeting")
def public_greeting(db: Session = Depends(get_db)):
    bot = get_bot_settings(db)
    return {"greeting": bot.greeting_ar}
