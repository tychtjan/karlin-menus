"""Czech to English translation of menu names via the Claude API."""

import json

import anthropic


class TranslationError(ValueError):
    """The translator's reply could not be trusted."""


def _names_to_translate(menu):
    """Names to send for one restaurant; an unavailable one is never rendered, so nothing is sent."""
    data = menu["data"]
    if not data.get("available"):
        return {"soup": None, "dishes": []}
    soup = data.get("soup")
    return {
        "soup": soup["name"] if soup else None,
        "dishes": [d["name"] for d in data.get("dishes") or []],
    }


def _parse_translation(reply, menus):
    """Return the translated name lists, or raise TranslationError if the shape differs."""
    text = reply.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        translated = json.loads(text)
    except json.JSONDecodeError:
        raise TranslationError(f"translator did not return JSON: {reply.strip()[:200]}")

    if not isinstance(translated, list) or len(translated) != len(menus):
        raise TranslationError("translated restaurant list does not match the input")

    def clean(name):
        if not isinstance(name, str) or not name.strip():
            raise TranslationError(f"translated name is not a non-empty string: {name!r}")
        return " ".join(name.split())

    result = []
    for menu, entry in zip(menus, translated):
        expected = _names_to_translate(menu)
        if not isinstance(entry, dict):
            raise TranslationError("translated restaurant entry is not an object")
        dishes = entry.get("dishes")
        if not isinstance(dishes, list) or len(dishes) != len(expected["dishes"]):
            raise TranslationError(f'dish count changed for {menu["name"]}')
        if (expected["soup"] is None) != (entry.get("soup") is None):
            raise TranslationError(f'soup presence changed for {menu["name"]}')
        result.append({
            "soup": None if expected["soup"] is None else clean(entry["soup"]),
            "dishes": [clean(d) for d in dishes],
        })
    return result


def translate_menus(menus, api_key):
    """Translate soup and dish names to English; prices and availability are never sent."""
    payload = [_names_to_translate(m) for m in menus]
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": (
                "Translate the soup and dish names in this JSON from Czech to English. "
                "Translate naturally using common English food terms "
                "(e.g. 'svíčková' → 'Marinated beef sirloin with cream sauce'). "
                "Keep the JSON structure, array order and array lengths exactly the same; "
                "keep null values as null. "
                "FAILSAFE: if any name contains encoding corruption (garbled sequences like "
                "'KuĹ™ecĂ­' instead of 'Kuřecí') or broken formatting, do NOT translate — "
                "output exactly 'VALIDATION_FAILED: <short reason>' and nothing else. "
                "Output ONLY the translated JSON, nothing else.\n\n"
                f"{json.dumps(payload, ensure_ascii=False)}"
            ),
        }],
    )
    names = _parse_translation(response.content[0].text, menus)

    translated = []
    for menu, n in zip(menus, names):
        data = menu["data"]
        if not data.get("available"):
            translated.append(menu)
            continue
        soup = data.get("soup")
        translated.append({
            **menu,
            "data": {
                **data,
                "soup": {**soup, "name": n["soup"]} if soup else None,
                "dishes": [{**d, "name": name} for d, name in zip(data.get("dishes") or [], n["dishes"])],
            },
        })
    return translated
