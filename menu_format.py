"""Pure formatting of menus into Slack mrkdwn and canvas Markdown."""

DIVIDER = "───────────────────────────────────"

LABELS = {
    "cs": {
        "title": "Obědová menu",
        "soup": "Polévka",
        "currency": "Kč",
        "unavailable": "Menu dnes není k dispozici",
        "canvas_link": "Otevřít v canvasu",
        "dish": "Jídlo",
        "price": "Cena",
    },
    "en": {
        "title": "Lunch Menus",
        "soup": "Soup",
        "currency": "CZK",
        "unavailable": "No menu available today",
        "canvas_link": "Open in canvas",
        "dish": "Dish",
        "price": "Price",
    },
}


def format_restaurant_mrkdwn(menu, labels):
    """Format a single restaurant's menu in Slack mrkdwn."""
    data = menu["data"]
    currency = labels["currency"]
    lines = [f'{menu["emoji"]} *{menu["name"]}*']

    if not data.get("available"):
        lines.append(labels["unavailable"])
        return "\n".join(lines)

    soup = data.get("soup")
    if soup:
        price_str = f" • *{soup['price']} {currency}*" if soup.get("price") else ""
        lines.append(f"_{labels['soup']}:_ {soup['name']}{price_str}")

    for i, dish in enumerate(data.get("dishes", []), 1):
        price_str = f" • *{dish['price']} {currency}*" if dish.get("price") else ""
        lines.append(f"{i}. {dish['name']}{price_str}")

    return "\n".join(lines)


def _table_row(*cells):
    return "| " + " | ".join(str(c).replace("|", "\\|") for c in cells) + " |"


def format_restaurant_canvas(menu, labels):
    """Format a single restaurant's menu in canvas Markdown, dishes as a table."""
    data = menu["data"]
    currency = labels["currency"]
    lines = [f'## {menu["emoji"]} {menu["name"]}', ""]

    if not data.get("available"):
        lines.append(labels["unavailable"])
        return "\n".join(lines)

    def price(item):
        return f"{item['price']} {currency}" if item.get("price") else ""

    lines += [_table_row("#", labels["dish"], labels["price"]), "|---|---|---|"]
    soup = data.get("soup")
    if soup:
        lines.append(_table_row(labels["soup"], soup["name"], price(soup)))
    for i, dish in enumerate(data.get("dishes", []), 1):
        lines.append(_table_row(i, dish["name"], price(dish)))

    return "\n".join(lines)


def build_message(menus, date_str, labels, canvas_id):
    """Build the full Slack mrkdwn message."""
    parts = [f":knife_fork_plate: *{labels['title']} — {date_str}*", ""]
    for menu in menus:
        parts.append(DIVIDER)
        parts.append(format_restaurant_mrkdwn(menu, labels))
        parts.append("")
    parts.append(DIVIDER)
    parts.append(f":bookmark: <https://gooddata.slack.com/docs/T02G0PHRH/{canvas_id}|{labels['canvas_link']}>")
    return "\n".join(parts)


def build_canvas(menus, date_str, labels):
    """Build the full canvas content."""
    parts = [f"# :knife_fork_plate: {labels['title']} — {date_str}", ""]
    for menu in menus:
        parts.append(format_restaurant_canvas(menu, labels))
        parts.append("")
    return "\n".join(parts)
