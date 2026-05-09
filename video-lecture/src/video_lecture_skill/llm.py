from __future__ import annotations

import logging

import httpx

from video_lecture_skill.config import SkillSettings

logger = logging.getLogger("video_lecture_skill.llm")


def chat_completion(
    settings: SkillSettings,
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1100,
    temperature: float = 0.28,
    require_json: bool = False,
    timeout: int = 60,
    fallback: str = "",
) -> str:
    config = settings.effective_knowledge_llm_config
    if not config["api_key"]:
        return fallback

    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }
    payload: dict[str, object] = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if require_json:
        payload["response_format"] = {"type": "json_object"}
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{config['base_url']}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return str(data.get("choices", [{}])[0].get("message", {}).get("content", "")).strip()
    except Exception as exc:
        logger.warning("LLM call failed: %s", exc)
        return fallback
