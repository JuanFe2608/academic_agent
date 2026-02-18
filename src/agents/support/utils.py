from typing import Any


def coerce_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item and isinstance(item["text"], str):
                parts.append(item["text"])
        return " ".join(parts)
    return ""
