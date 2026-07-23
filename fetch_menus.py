#!/usr/bin/env python3
"""Fetch daily lunch menus from 6 Karlín restaurants and save as JSON."""

import base64
import json
import os
import re
from datetime import date, datetime

import anthropic
import requests
from bs4 import BeautifulSoup

MENUS_DIR = os.path.join(os.path.dirname(__file__), "menus")
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:148.0) Gecko/20100101 Firefox/148.0"
HEADERS = {"User-Agent": USER_AGENT}

# Czech day names (lowercase) indexed by weekday (0=Monday)
CZECH_DAYS = ["pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota", "neděle"]


def collapse_whitespace(text: str) -> str:
    """Collapse newlines/indentation from HTML source into single spaces."""
    return re.sub(r"\s+", " ", text).strip()


def fetch_menicka(url: str, restaurant_name: str) -> dict:
    """Fetch and parse a daily menu from menicka.cz."""
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")

    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    # Parse from raw bytes so BeautifulSoup picks up the charset declared in
    # the HTML (menicka.cz switched from windows-1250 to utf-8)
    soup_html = BeautifulSoup(resp.content, "html.parser")

    # menicka.cz structure:
    # <div class="menicka">
    #   <div class="nadpis">Pondělí 30.3.2026</div>
    #   <ul>
    #     <li class="polevka"><div class="polozka">...</div><div class="cena">55 Kč</div></li>
    #     <li class="jidlo"><div class="polozka">...</div><div class="cena">275 Kč</div></li>
    #   </ul>
    # </div>
    menicka_divs = soup_html.find_all("div", class_="menicka")

    today_weekday = CZECH_DAYS[today.weekday()]
    today_day = today.day
    today_month = today.month
    date_pattern = f"{today_day}.{today_month}."

    target_div = None
    for div in menicka_divs:
        nadpis = div.find("div", class_="nadpis")
        if not nadpis:
            continue
        heading_text = nadpis.get_text().lower().strip()
        if today_weekday in heading_text or date_pattern in heading_text:
            target_div = div
            break

    if not target_div:
        return {
            "date": today_str,
            "restaurant": restaurant_name,
            "available": False,
            "soup": None,
            "dishes": [],
        }

    # Extract menu items from <li> elements
    soup_item = None
    dishes = []

    for li in target_div.find_all("li"):
        polozka = li.find("div", class_="polozka")
        cena = li.find("div", class_="cena")

        if not polozka:
            continue

        # Remove allergen <em> tags before extracting text
        for em in polozka.find_all("em"):
            em.decompose()

        item_text = collapse_whitespace(polozka.get_text(" ", strip=True))
        price = None
        if cena:
            digits = re.search(r"(\d+)", cena.get_text(strip=True))
            if digits:
                price = int(digits.group(1))

        if not item_text:
            continue

        # Clean name: remove leading number + dot/weight prefix like "1.180g "
        clean_name = re.sub(r"^\d+\.\s*(?:\d+g\s+)?", "", item_text).strip()
        # Also handle "1. 180g ..." pattern
        clean_name = re.sub(r"^\d+g\s+", "", clean_name).strip()
        # Remove trailing allergen codes like "*1a, 7, 9" or "*3, 6, 7"
        clean_name = re.sub(r"\s*\*[\d,a-z\s]+$", "", clean_name).strip()

        li_classes = " ".join(li.get("class", []))
        if "polevka" in li_classes and soup_item is None:
            soup_item = {"name": clean_name, "price": price}
        else:
            dishes.append({"name": clean_name, "price": price})

    return {
        "date": today_str,
        "restaurant": restaurant_name,
        "available": True,
        "soup": soup_item,
        "dishes": dishes,
    }


def fetch_tankovna() -> dict:
    """Fetch daily menu from Tankovna Karlín via Sanity CMS API."""
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")

    api_url = (
        "https://8xyahh9y.api.sanity.io/v2024-01-01/data/query/production"
        f'?query=*%5B_type+%3D%3D+%22lunchMenu%22+%26%26+date+%3D%3D+%24today%5D%5B0%5D'
        f"&%24today=%22{today_str}%22&returnQuery=false"
    )

    resp = requests.get(api_url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    result = data.get("result")
    if not result:
        return {
            "date": today_str,
            "restaurant": "Tankovna Karlín",
            "available": False,
            "soup": None,
            "dishes": [],
        }

    soup_data = result.get("soup")
    soup_item = None
    if soup_data:
        soup_item = {
            "name": soup_data.get("name", "").title(),
            "price": soup_data.get("price"),
        }

    dishes = []
    for dish in result.get("dishes", []):
        dishes.append({
            "name": dish.get("name", "").title(),
            "price": dish.get("price"),
        })

    return {
        "date": today_str,
        "restaurant": "Tankovna Karlín",
        "available": True,
        "soup": soup_item,
        "dishes": dishes,
    }


def fetch_jidlovice() -> dict:
    """Fetch daily menu from Jídlovice Karlín via REST API."""
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")

    api_url = (
        f"https://www.jidlovice.cz/api/v1/branch/2/menu/{today_str}"
        "?include_internal_tags=false"
    )

    resp = requests.get(api_url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    menu_items = data.get("menu_items", [])
    if not menu_items:
        return {
            "date": today_str,
            "restaurant": "Jídlovice Karlín",
            "available": False,
            "soup": None,
            "dishes": [],
        }

    soup_item = None
    dishes = []

    for item in menu_items:
        meal = item.get("meal", {})
        name = (meal.get("name") or "").strip()
        desc = (meal.get("description") or "").strip()
        full_name = f"{name}, {desc}" if desc else name
        price = meal.get("price")
        category_id = meal.get("category_id")

        if category_id == 1 and soup_item is None:
            soup_item = {"name": full_name, "price": price}
        elif category_id == 4 and price is not None:
            dishes.append({"name": full_name, "price": price})

    return {
        "date": today_str,
        "restaurant": "Jídlovice Karlín",
        "available": bool(soup_item or dishes),
        "soup": soup_item,
        "dishes": dishes,
    }


# San Carlo pre-uploads several weekly menu images in one batch and cycles
# which filename is current (e.g. menu.png = week 1, menu_1.png = week 2, ...).
SANCARLO_MENU_CANDIDATES = ["menu.png"] + [f"menu_{i}.png" for i in range(1, 7)]


def _parse_day_month(value) -> tuple | None:
    """Parse a 'DD.MM' or 'DD.MM.' string into (day, month), or None."""
    if not isinstance(value, str):
        return None
    match = re.match(r"\s*(\d{1,2})\.\s*(\d{1,2})\.?\s*$", value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def menu_covers_today(valid_from, valid_to, today: date) -> bool:
    """Check whether a menu's printed 'DD.MM – DD.MM' validity range covers today.

    The images omit the year, so pick the year that puts the start date closest
    to today, and let the end date roll into the next year for ranges that wrap
    (e.g. 29.12 – 02.01).
    """
    parsed_from = _parse_day_month(valid_from)
    parsed_to = _parse_day_month(valid_to)
    if not parsed_from or not parsed_to:
        return False

    start_candidates = []
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            start_candidates.append(date(year, parsed_from[1], parsed_from[0]))
        except ValueError:
            pass
    if not start_candidates:
        return False
    start = min(start_candidates, key=lambda d: abs((d - today).days))

    try:
        end = date(start.year, parsed_to[1], parsed_to[0])
        if end < start:
            end = date(start.year + 1, parsed_to[1], parsed_to[0])
    except ValueError:
        return False

    return start <= today <= end


def _extract_sancarlo_menu(client, image_b64: str) -> dict | None:
    """Run Claude vision on one menu image; return parsed JSON or None."""
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": image_b64},
                },
                {
                    "type": "text",
                    "text": (
                        "Extract the menu items from this restaurant menu image. "
                        "Under the MENU title there is a validity date range like '01.06 – 05.06.'. "
                        "Each item has an Italian name and a Czech description below it. "
                        "Return ONLY valid JSON in this exact format, nothing else:\n"
                        '{"valid_from": "01.06", "valid_to": "05.06", '
                        '"soup": {"name": "Italian name — Czech description", "price": 75}, '
                        '"dishes": [{"name": "Italian name — Czech description", "price": 215}]}\n'
                        "Rules:\n"
                        "- valid_from/valid_to are the DD.MM dates printed on the image; "
                        "if no date range is visible, use null for both\n"
                        "- Combine the Italian name and Czech description with ' — ' separator\n"
                        "  Example: 'Penne al Forno — těstoviny penne, rajčata, mozzarella, bazalka'\n"
                        "- Prices are integers in CZK\n"
                        "- If there's a soup/zuppa, put it in soup field\n"
                        "- Put pasta, pizza, and other items in dishes array\n"
                        "- Remove allergen numbers like (1, 7) from names\n"
                        "- If the menu image is blank or unreadable, return: "
                        '{"valid_from": null, "valid_to": null, "soup": null, "dishes": []}'
                    ),
                },
            ],
        }],
    )

    try:
        raw = message.content[0].text.strip()
        # Handle markdown code blocks
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except (json.JSONDecodeError, IndexError) as e:
        print(f"  San Carlo: failed to parse Claude response: {e}")
        return None


def fetch_sancarlo() -> dict:
    """Fetch weekly menu from San Carlo by reading their menu PNGs with Claude vision.

    Tries each candidate image, extracts the printed validity range, and uses
    the one whose range covers today. Marks the menu unavailable if no image
    covers today (e.g. the restaurant hasn't uploaded this week's menu yet).
    """
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    unavailable = {"date": today_str, "restaurant": "San Carlo", "available": False, "soup": None, "dishes": []}

    api_key = os.environ.get("CLAUDE_API_KEY")
    if not api_key:
        print("  San Carlo: CLAUDE_API_KEY not set, skipping")
        return unavailable

    client = anthropic.Anthropic(api_key=api_key)

    for filename in SANCARLO_MENU_CANDIDATES:
        resp = requests.get(f"https://sancarlo.cz/{filename}", headers=HEADERS, timeout=15)
        if resp.status_code != 200 or "image" not in resp.headers.get("content-type", ""):
            continue

        image_b64 = base64.b64encode(resp.content).decode("utf-8")
        data = _extract_sancarlo_menu(client, image_b64)
        if data is None:
            continue

        valid_from, valid_to = data.get("valid_from"), data.get("valid_to")
        if not menu_covers_today(valid_from, valid_to, today):
            print(f"  San Carlo: {filename} covers {valid_from}–{valid_to}, not today — trying next")
            continue

        print(f"  San Carlo: using {filename} (valid {valid_from}–{valid_to})")
        return {
            "date": today_str,
            "restaurant": "San Carlo",
            "available": bool(data.get("soup") or data.get("dishes")),
            "soup": data.get("soup"),
            "dishes": data.get("dishes", []),
        }

    print("  San Carlo: no menu image covers today")
    return unavailable


def save_menu(filename: str, data: dict) -> None:
    """Save menu data to JSON file."""
    os.makedirs(MENUS_DIR, exist_ok=True)
    filepath = os.path.join(MENUS_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Saved {filepath}")


def main():
    today = date.today()
    weekday = today.weekday()

    if weekday >= 5:
        print(f"Today is {CZECH_DAYS[weekday]}, skipping (no lunch menus on weekends).")
        return

    print(f"Fetching menus for {today.isoformat()} ({CZECH_DAYS[weekday]})...")

    # Fetch Pivo Karlín
    try:
        pivo = fetch_menicka("https://www.menicka.cz/6912-pivo-karlin.html", "Pivo Karlín")
        print(f"  Pivo Karlín: {len(pivo['dishes'])} dishes")
    except Exception as e:
        print(f"  Pivo Karlín FAILED: {e}")
        pivo = {"date": today.isoformat(), "restaurant": "Pivo Karlín", "available": False, "soup": None, "dishes": []}

    # Fetch Diego Pivní Bar
    try:
        diego = fetch_menicka("https://www.menicka.cz/7191-diego-pivni-bar.html", "Diego Pivní Bar")
        print(f"  Diego Pivní Bar: {len(diego['dishes'])} dishes")
    except Exception as e:
        print(f"  Diego Pivní Bar FAILED: {e}")
        diego = {"date": today.isoformat(), "restaurant": "Diego Pivní Bar", "available": False, "soup": None, "dishes": []}

    # Fetch Tankovna Karlín
    try:
        tankovna = fetch_tankovna()
        print(f"  Tankovna Karlín: {len(tankovna['dishes'])} dishes")
    except Exception as e:
        print(f"  Tankovna Karlín FAILED: {e}")
        tankovna = {"date": today.isoformat(), "restaurant": "Tankovna Karlín", "available": False, "soup": None, "dishes": []}

    # Fetch Dvorek Karlín
    try:
        dvorek = fetch_menicka("https://www.menicka.cz/2427-dvorek-karlin.html", "Dvorek Karlín")
        # Filter out section headers (items with no price like "Týdenní speciály")
        dvorek["dishes"] = [d for d in dvorek["dishes"] if d["price"] is not None]
        # Normalize ALLCAPS dish names to sentence case
        if dvorek.get("soup"):
            dvorek["soup"]["name"] = dvorek["soup"]["name"].capitalize()
        for d in dvorek["dishes"]:
            d["name"] = d["name"].capitalize()
        print(f"  Dvorek Karlín: {len(dvorek['dishes'])} dishes")
    except Exception as e:
        print(f"  Dvorek Karlín FAILED: {e}")
        dvorek = {"date": today.isoformat(), "restaurant": "Dvorek Karlín", "available": False, "soup": None, "dishes": []}

    # Fetch Jídlovice Karlín
    try:
        jidlovice = fetch_jidlovice()
        print(f"  Jídlovice Karlín: {len(jidlovice['dishes'])} dishes")
    except Exception as e:
        print(f"  Jídlovice Karlín FAILED: {e}")
        jidlovice = {"date": today.isoformat(), "restaurant": "Jídlovice Karlín", "available": False, "soup": None, "dishes": []}

    # Fetch San Carlo
    try:
        sancarlo = fetch_sancarlo()
        print(f"  San Carlo: {len(sancarlo['dishes'])} dishes")
    except Exception as e:
        print(f"  San Carlo FAILED: {e}")
        sancarlo = {"date": today.isoformat(), "restaurant": "San Carlo", "available": False, "soup": None, "dishes": []}

    save_menu("pivo.json", pivo)
    save_menu("diego.json", diego)
    save_menu("tankovna.json", tankovna)
    save_menu("dvorek.json", dvorek)
    save_menu("jidlovice.json", jidlovice)
    save_menu("sancarlo.json", sancarlo)

    print("Done!")


if __name__ == "__main__":
    main()
