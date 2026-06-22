import logging

from fastapi import HTTPException
from openai import OpenAIError
from app.services.openai_client import get_openai_client

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

PROMPT_ENHANCE_SYSTEM = (
    "You are an expert at writing system prompts for customer service chatbots. "
    "Given the current English system prompt and the admin's plain-language instruction, "
    "produce an updated complete system prompt in English. "
    "Merge the new rule naturally into the existing instructions without removing important rules. "
    "Return ONLY the full updated system prompt text, no explanations or markdown."
)


async def enhance_prompt(base_prompt: str, instruction: str) -> str:
    if not instruction.strip():
        raise HTTPException(status_code=400, detail="Instruction is empty")

    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="AI service unavailable")

    client = get_openai_client()
    user_content = f"Current system prompt:\n\n{base_prompt}\n\nAdmin instruction to apply:\n\n{instruction}"

    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": PROMPT_ENHANCE_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
        )
    except OpenAIError as exc:
        logger.warning("Prompt enhance failed: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to enhance prompt") from exc

    return response.choices[0].message.content or base_prompt
