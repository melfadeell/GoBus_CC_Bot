import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from app.auth import get_current_customer_optional
from app.config import get_settings
from app.core.constants import CHAT_ERROR_MESSAGE
from app.core.rate_limit import get_client_ip, limiter

settings = get_settings()
from app.database import SessionLocal
from app.models.models import Customer
from app.schemas.schemas import ChatRequest, DestinationStationsOut, OcrResponse, StationCardOut
from app.services.chat_service import ChatProcessingError, stream_chat_response
from app.services.kb_retrieval import _resolve_route_destination, stations_for_destination
from app.services.chat_uploads import resolve_attachment_path, save_chat_image
from app.services.ocr_service import (
    ALLOWED_IMAGE_TYPES,
    MAX_IMAGE_BYTES,
    extract_text_from_image,
    tesseract_available,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/upload-image")
async def chat_upload_image(file: UploadFile = File(...)):
    image_url = await save_chat_image(file)
    return {"image_url": image_url}


@router.get("/attachments/{filename}")
def get_chat_attachment(filename: str):
    path = resolve_attachment_path(filename)
    return FileResponse(path)


@router.post("/ocr", response_model=OcrResponse)
async def chat_ocr(file: UploadFile = File(...)):
    if not tesseract_available():
        raise HTTPException(
            status_code=503,
            detail="OCR is not available. Install Tesseract OCR on the server.",
        )

    content_type = file.content_type or ""
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported image type. Use JPEG, PNG, or WebP.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Image too large (max 5 MB)")

    try:
        # OCR (tesseract) is CPU-bound and blocking — run it off the event loop.
        text = await asyncio.to_thread(extract_text_from_image, data)
    except Exception as exc:
        logger.warning("OCR failed: %s", exc)
        raise HTTPException(status_code=422, detail="Could not read text from image") from exc

    return OcrResponse(text=text)


@router.get("/destination-stations", response_model=DestinationStationsOut)
@limiter.limit(settings.rate_limit_chat)
def destination_stations(
    request: Request,
    destination: str = Query(..., min_length=1, max_length=255),
):
    canonical = _resolve_route_destination(destination)
    if not canonical:
        raise HTTPException(status_code=404, detail="Destination not found")
    cards = stations_for_destination(destination)
    return DestinationStationsOut(
        destination=canonical,
        stations=[StationCardOut(**c) for c in cards],
    )


@router.post("/stream")
@limiter.limit(settings.rate_limit_chat)
async def chat_stream(
    request: Request,
    payload: ChatRequest,
    customer: Customer | None = Depends(get_current_customer_optional),
):
    session_id = payload.session_id or str(uuid.uuid4())
    user_message = payload.message.strip()
    ocr_text = payload.ocr_text
    image_url = payload.image_url
    client_ip = get_client_ip(request)
    request_id = getattr(request.state, "request_id", None)
    # Resolve customer identity to primitives now — the request-scoped DB session
    # closes before the generator below runs, so don't touch the ORM object later.
    customer_id = customer.id if customer else None
    customer_name = customer.full_name if customer else None
    customer_email = customer.email if customer else None

    async def event_generator():
        yield {"event": "session", "data": json.dumps({"session_id": session_id})}

        db = SessionLocal()
        # Stop work (and free the DB session) if the client disconnects mid-stream.
        cancelled = {"flag": False}

        def is_cancelled() -> bool:
            return cancelled["flag"]

        try:
            async for event in stream_chat_response(
                db,
                session_id,
                user_message,
                ocr_text=ocr_text,
                image_url=image_url,
                channel=payload.channel,
                client_ip=client_ip,
                request_id=request_id,
                cancelled=is_cancelled,
                customer_id=customer_id,
                customer_name=customer_name,
                customer_email=customer_email,
            ):
                if await request.is_disconnected():
                    cancelled["flag"] = True
                    break
                if event["type"] == "token":
                    yield {"event": "token", "data": json.dumps({"content": event["content"]})}
                elif event["type"] == "meta":
                    meta_payload = {k: v for k, v in event.items() if k != "type"}
                    yield {"event": "meta", "data": json.dumps(meta_payload)}
            yield {"event": "done", "data": json.dumps({"session_id": session_id})}
        except ChatProcessingError as exc:
            logger.warning("Chat processing error: %s", exc)
            yield {"event": "error", "data": json.dumps({"error": CHAT_ERROR_MESSAGE})}
            yield {"event": "done", "data": json.dumps({"session_id": session_id})}
        except Exception:
            logger.exception("Unexpected chat stream error")
            yield {"event": "error", "data": json.dumps({"error": CHAT_ERROR_MESSAGE})}
            yield {"event": "done", "data": json.dumps({"session_id": session_id})}
        finally:
            db.close()

    return EventSourceResponse(
        event_generator(),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
