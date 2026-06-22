import logging

from fastapi import HTTPException
from openai import OpenAIError
from app.services.openai_client import get_openai_client

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

ENHANCE_PROMPT = (
    "Refine the following text for a GoBus customer service knowledge base. "
    "Keep all facts and details. Make it clearer, more professional, and well-structured. "
    "Return only the improved Arabic text without explanations."
)


async def enhance_text(text: str) -> str:
    if not text.strip():
        raise HTTPException(status_code=400, detail="النص فارغ")

    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="خدمة الذكاء الاصطناعي غير متوفرة")

    client = get_openai_client()
    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": ENHANCE_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.2,
        )
    except OpenAIError as exc:
        logger.warning("Text enhance failed: %s", exc)
        raise HTTPException(status_code=502, detail="فشل تحسين النص") from exc

    return response.choices[0].message.content or text
