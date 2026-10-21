#!/usr/bin/env python3
"""Slack Block Kit builders for the daily lunch menu message.

Pure functions: inputs are never mutated and every returned structure is new.
"""

CANVAS_URL = "https://gooddata.slack.com/docs/T02G0PHRH/{canvas_id}"
NO_PRICE = "–"

MAX_TABLE_CHARS = 9000
MAX_BLOCKS = 50
MAX_ROWS = 100


def _section(text):
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _cell(text):
    return {"type": "raw_text", "text": text}


def _price(price, currency):
    """Slack rejects empty raw_text cells, so a missing price gets a placeholder."""
    return f"{price} {currency}" if price else NO_PRICE


def _menu_rows(data, labels):
    """Text rows for one available restaurant: soup first, then numbered dishes."""
    currency = labels["currency"]
    rows = []
    soup = data.get("soup")
    if soup:
        rows.append([labels["soup"], soup["name"], _price(soup.get("price"), currency)])
    for i, dish in enumerate(data.get("dishes") or [], start=1):
        rows.append([str(i), dish["name"], _price(dish.get("price"), currency)])
    return rows


def _table(text_rows, column_settings):
    return {
        "type": "table",
        "rows": [[_cell(text) for text in row] for row in text_rows],
        "column_settings": column_settings,
    }


def _per_restaurant_blocks(menus, labels):
    header = ["#", labels["dish"], labels["price"]]
    settings = [{"align": "left"}, {"is_wrapped": True}, {"align": "right"}]
    blocks = []
    for menu in menus:
        title = f'{menu["emoji"]} *{menu["name"]}*'
        if not menu["data"].get("available"):
            blocks.append(_section(f'{title}\n{labels["unavailable"]}'))
            continue
        blocks.append(_section(title))
        blocks.append(_table([header, *_menu_rows(menu["data"], labels)], settings))
    return blocks


def build_blocks(menus, date_str, labels, canvas_id):
    """Build the full block list: title, restaurant content, canvas footer.

    Each restaurant is a section followed by a table; an unavailable
    restaurant gets only a section.
    """
    title = _section(f':knife_fork_plate: *{labels["title"]} — {date_str}*')
    link = f'<{CANVAS_URL.format(canvas_id=canvas_id)}|{labels["canvas_link"]}>'
    return [title, *_per_restaurant_blocks(menus, labels), _section(link)]


def table_chars(blocks):
    """Total characters of cell text across all table blocks."""
    return sum(
        len(cell["text"])
        for block in blocks
        if block["type"] == "table"
        for row in block["rows"]
        for cell in row
    )


def _row_count(blocks):
    return sum(len(b["rows"]) for b in blocks if b["type"] == "table")


def _restaurant_groups(body):
    """Split blocks into restaurant groups.

    A group is a section block immediately followed by a table block, or any
    other single block (an unavailable restaurant's lone section).
    """
    groups = []
    i = 0
    while i < len(body):
        paired = (
            body[i]["type"] == "section"
            and i + 1 < len(body)
            and body[i + 1]["type"] == "table"
        )
        groups.append(body[i : i + 2] if paired else body[i : i + 1])
        i += 2 if paired else 1
    return groups


def _shorten(text, limit):
    """Cut text to at most limit characters at a word boundary, ending in an ellipsis."""
    if len(text) <= limit:
        return text
    cut = text[: max(limit - 1, 0)]
    if " " in cut and text[len(cut)] != " ":
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip() + "…"


def _limit_dish_names(block, limit):
    """Copy of block with the dish column (second to last) cut to limit characters."""
    if block["type"] != "table":
        return block
    col = len(block["column_settings"]) - 2
    rows = [
        [
            _cell(_shorten(cell["text"], limit)) if j == col and i > 0 else dict(cell)
            for j, cell in enumerate(row)
        ]
        for i, row in enumerate(block["rows"])
    ]
    return {**block, "rows": rows}


def _fit_group(group, max_chars):
    """Truncate dish names, longest allowed first, until the group fits max_chars."""
    if table_chars(group) <= max_chars:
        return group
    longest = max(
        len(cell["text"])
        for block in group
        if block["type"] == "table"
        for row in block["rows"]
        for cell in row
    )
    lo, hi = 1, longest
    while lo < hi:
        mid = (lo + hi + 1) // 2
        trial = [_limit_dish_names(b, mid) for b in group]
        if table_chars(trial) <= max_chars:
            lo = mid
        else:
            hi = mid - 1
    return [_limit_dish_names(b, lo) for b in group]


def chunk_blocks(
    blocks, max_table_chars=MAX_TABLE_CHARS, max_blocks=MAX_BLOCKS, max_rows=MAX_ROWS
):
    """Split build_blocks output into messages that respect Slack's limits.

    blocks[0] is the title and blocks[-1] the footer; the title goes only into
    the first chunk and the footer only into the last. The blocks between are
    split into restaurant groups (see _restaurant_groups) that are never torn
    apart. max_table_chars and max_rows count table cells and rows per chunk.
    A group that alone exceeds max_table_chars gets its dish names truncated;
    rows are never dropped.
    """
    if len(blocks) < 2:
        return [list(blocks)]
    title, body, footer = blocks[0], blocks[1:-1], blocks[-1]
    chunks = [[title]]
    chars = rows = count = 0
    for group in (_fit_group(g, max_table_chars) for g in _restaurant_groups(body)):
        group_chars, group_rows = table_chars(group), _row_count(group)
        overflow = (
            len(chunks[-1]) + len(group) > max_blocks
            or chars + group_chars > max_table_chars
            or rows + group_rows > max_rows
        )
        if overflow and count:
            chunks.append([])
            chars = rows = count = 0
        chunks[-1].extend(group)
        chars, rows, count = chars + group_chars, rows + group_rows, count + 1
    if len(chunks[-1]) + 1 > max_blocks:
        chunks.append([])
    chunks[-1].append(footer)
    return chunks
