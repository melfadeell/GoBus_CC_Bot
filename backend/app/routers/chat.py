import json
import logging
import uuid

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from app.core.constants import CHAT_ERROR_MESSAGE
from app.core.rate_limit import get_client_ip, limiter
from app.database import SessionLocal
from app.schemas.schemas import ChatRequest, OcrResponse
from app.services.chat_service import ChatProcessingError, stream_chat_response
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
        text = extract_text_from_image(data)
    except Exception as exc:
        logger.warning("OCR failed: %s", exc)
        raise HTTPException(status_code=422, detail="Could not read text from image") from exc

    return OcrResponse(text=text)


@router.post("/stream")
@limiter.limit("15/minute")
async def chat_stream(request: Request, payload: ChatRequest):
    session_id = payload.session_id or str(uuid.uuid4())
    user_message = payload.message.strip()
    ocr_text = payload.ocr_text
    image_url = payload.image_url
    client_ip = get_client_ip(request)
    request_id = getattr(request.state, "request_id", None)

    async def event_generator():
        yield {"event": "session", "data": json.dumps({"session_id": session_id})}

        db = SessionLocal()
        try:
            async for token in stream_chat_response(
                db,
                session_id,
                user_message,
                ocr_text=ocr_text,
                image_url=image_url,
                channel=payload.channel,
                client_ip=client_ip,
                request_id=request_id,
            ):
                yield {"event": "token", "data": json.dumps({"content": token})}
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
