from __future__ import annotations

import json
import logging

import httpx

from video_lecture_skill.config import SkillSettings

logger = logging.getLogger("video_lecture_skill.llm")


def extract_json(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    for attempt_text in [content.strip(), text]:
        if not attempt_text:
            continue
        try:
            return json.loads(attempt_text)
        except json.JSONDecodeError:
            try:
                return json.loads(attempt_text, strict=False)
            except json.JSONDecodeError:
                continue
    raise RuntimeError("LLM returned invalid JSON")


def safe_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


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
