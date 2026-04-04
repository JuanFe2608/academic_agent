"""Genera una tabla semanal simple a partir de eventos.

Un renderer es un componente que toma datos y los dibuja en un formato
visual. Aqui se crea una imagen PNG con una tabla de dias y bloques de hora.
"""

from __future__ import annotations

import os
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

from agents.support.scheduling.calendar_logic import (
    ScheduledOccurrence,
    WeekDaySlot,
    format_day_header,
    format_week_title,
    resolve_weekly_events_to_current_week,
)
from agents.support.scheduling.event_labels import normalize_activity_label
from schemas.scheduling import Event
from services.scheduling.validation import normalize_time, sort_events

COLOR_BY_CATEGORY = {
    "laboral": ((244, 124, 94), (255, 232, 223)),
    "academico": ((78, 152, 118), (225, 244, 232)),
    "extracurricular": ((73, 117, 201), (228, 237, 255)),
    "estudio": ((220, 168, 61), (255, 245, 215)),
}
BACKGROUND_COLOR = (245, 247, 250)
PANEL_COLOR = (255, 255, 255)
GRID_COLOR = (212, 218, 228)
HEADER_FILL = (23, 37, 61)
HEADER_TEXT = (248, 250, 252)
TEXT_COLOR = (34, 43, 58)
MUTED_TEXT = (97, 109, 126)
HOUR_BAND = (238, 242, 247)


def render_week_schedule(
    events: list[Event],
    out_dir: str = "tmp",
    filename: str = "schedule.png",
    start_hour: int = 0,
    end_hour: int = 24,
    timezone_name: str = "America/Bogota",
    reference: datetime | None = None,
) -> str:
    """Genera una tabla semanal con eventos y retorna el PNG generado.

    El rango visible por defecto es 00:00 a 23:59. Los eventos que caen fuera
    de este rango se recortan al borde visible o se omiten si quedan fuera.
    """

    os.makedirs(out_dir, exist_ok=True)
    if end_hour <= start_hour:
        raise ValueError("end_hour must be greater than start_hour")
    ordered = sort_events(events)
    slots, occurrences = resolve_weekly_events_to_current_week(
        ordered,
        timezone_name,
        reference,
    )
    days = [slot.day_name for slot in slots]
    hour_count = end_hour - start_hour

    width = 1200
    height = 828
    left_margin = 92
    right_margin = 24
    top_margin = 62
    bottom_margin = 26
    header_height = 58
    row_height = int((height - top_margin - bottom_margin - header_height) / hour_count)
    col_width = int((width - left_margin - right_margin) / len(days))

    image = Image.new("RGB", (width, height), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(image)
    fonts = _load_fonts()

    _draw_background(draw, width, height)

    _draw_grid(
        draw,
        slots,
        width,
        height,
        left_margin,
        right_margin,
        top_margin,
        bottom_margin,
        header_height,
        row_height,
        start_hour,
        fonts,
        format_week_title(slots),
    )

    for occurrence in occurrences:
        _draw_event(
            draw,
            occurrence,
            days,
            left_margin,
            top_margin,
            header_height,
            col_width,
            row_height,
            start_hour,
            end_hour,
            fonts,
        )

    path = os.path.join(out_dir, filename)
    image.save(path, "PNG")
    return path


def _draw_grid(
    draw: ImageDraw.ImageDraw,
    slots: list[WeekDaySlot],
    width: int,
    height: int,
    left_margin: int,
    right_margin: int,
    top_margin: int,
    bottom_margin: int,
    header_height: int,
    row_height: int,
    start_hour: int,
    fonts: dict[str, ImageFont.ImageFont],
    title: str,
) -> None:
    """Dibuja la tabla base con cabeceras y lineas de hora."""
    panel = [12, 12, width - 12, height - 12]
    draw.rounded_rectangle(panel, radius=24, fill=PANEL_COLOR, outline=(224, 229, 236), width=2)

    grid_left = left_margin
    grid_top = top_margin
    grid_right = width - right_margin
    grid_bottom = height - bottom_margin

    draw.rounded_rectangle(
        [grid_left, grid_top, grid_right, grid_top + header_height],
        radius=18,
        fill=HEADER_FILL,
    )

    if title:
        draw.text((left_margin, 22), title, fill=TEXT_COLOR, font=fonts["subtitle"])

    for idx, slot in enumerate(slots):
        x0 = left_margin + idx * int((grid_right - grid_left) / len(slots))
        x1 = left_margin + (idx + 1) * int((grid_right - grid_left) / len(slots))
        if idx > 0:
            draw.line([x0, grid_top, x0, grid_bottom], fill=GRID_COLOR, width=1)
        first_line, second_line = format_day_header(slot)
        text_bbox = draw.textbbox((0, 0), first_line, font=fonts["day"])
        text_width = text_bbox[2] - text_bbox[0]
        draw.text(
            (x0 + ((x1 - x0) - text_width) / 2, grid_top + 10),
            first_line,
            fill=HEADER_TEXT,
            font=fonts["day"],
        )
        second_bbox = draw.textbbox((0, 0), second_line, font=fonts["date"])
        second_width = second_bbox[2] - second_bbox[0]
        draw.text(
            (x0 + ((x1 - x0) - second_width) / 2, grid_top + 31),
            second_line,
            fill=(204, 213, 225),
            font=fonts["date"],
        )

    hour_count = int((grid_bottom - grid_top - header_height) / row_height)
    for hour in range(hour_count + 1):
        y = grid_top + header_height + hour * row_height
        draw.line([grid_left, y, grid_right, y], fill=GRID_COLOR, width=1)
        if hour < hour_count:
            label = f"{start_hour + hour:02d}:00"
            label_y = y + max(4, int((row_height - 12) / 2) - 2)
            draw.rounded_rectangle(
                [20, y + 4, left_margin - 14, y + row_height - 4],
                radius=10,
                fill=HOUR_BAND,
            )
            draw.text((30, label_y), label, fill=MUTED_TEXT, font=fonts["hour"])


def _draw_background(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    """Agrega acentos suaves al fondo para evitar un lienzo plano."""
    draw.ellipse([-120, -80, 260, 220], fill=(229, 237, 247))
    draw.ellipse([width - 240, height - 220, width + 120, height + 80], fill=(237, 232, 223))
    draw.rectangle([0, 0, width, height], outline=(230, 234, 240))


def _draw_event(
    draw: ImageDraw.ImageDraw,
    occurrence: ScheduledOccurrence,
    days: list[str],
    left_margin: int,
    top_margin: int,
    header_height: int,
    col_width: int,
    row_height: int,
    start_hour: int,
    end_hour: int,
    fonts: dict[str, ImageFont.ImageFont],
) -> None:
    """Dibuja un bloque de evento dentro de la tabla semanal."""
    event = occurrence.event
    day = event.get("dia")
    if day not in days:
        return

    start = normalize_time(event.get("inicio", "00:00"))
    end = normalize_time(event.get("fin", "00:00"))
    start_minutes = int(start[:2]) * 60 + int(start[3:])
    end_minutes = int(end[:2]) * 60 + int(end[3:])

    visible_start = start_hour * 60
    visible_end = end_hour * 60
    start_minutes = max(start_minutes, visible_start)
    end_minutes = min(end_minutes, visible_end)
    if end_minutes <= start_minutes:
        return

    day_index = days.index(day)
    x0 = left_margin + day_index * col_width
    x1 = x0 + col_width

    y0 = top_margin + header_height + int(((start_minutes - visible_start) / 60) * row_height)
    y1 = top_margin + header_height + int(((end_minutes - visible_start) / 60) * row_height)

    accent, fill = COLOR_BY_CATEGORY.get(event.get("categoria"), ((73, 117, 201), (228, 237, 255)))
    block = [x0 + 8, y0 + 4, x1 - 8, y1 - 4]
    if block[3] - block[1] < 20:
        block[3] = block[1] + 20
    draw.rounded_rectangle(
        block,
        radius=16,
        fill=fill,
        outline=accent,
        width=2,
    )
    draw.rounded_rectangle(
        [block[0], block[1], block[0] + 7, block[3]],
        radius=16,
        fill=accent,
    )

    title = normalize_activity_label(
        str(event.get("titulo", "")).strip() or "Sin titulo",
        str(event.get("categoria", "")).strip(),
    )
    content_padding_x = 14
    content_padding_y = 8
    max_width = int(block[2] - block[0] - (content_padding_x * 2))
    max_height = int(block[3] - block[1] - (content_padding_y * 2))

    wrapped_title = _wrap_text(draw, title, fonts["title"], max_width)
    wrapped_title = _fit_wrapped_lines(draw, wrapped_title, fonts["title"], max_width, max_height)
    _draw_centered_multiline_text(
        draw,
        wrapped_title,
        block,
        fonts["title"],
        TEXT_COLOR,
        padding_x=content_padding_x,
        padding_y=content_padding_y,
    )


def _load_fonts() -> dict[str, ImageFont.ImageFont]:
    """Carga una familia legible; usa fallback si no hay TTF disponible."""
    try:
        return {
            "day": ImageFont.truetype("DejaVuSans-Bold.ttf", 18),
            "hour": ImageFont.truetype("DejaVuSans.ttf", 13),
            "time": ImageFont.truetype("DejaVuSans-Bold.ttf", 13),
            "title": ImageFont.truetype("DejaVuSans.ttf", 14),
            "date": ImageFont.truetype("DejaVuSans.ttf", 12),
            "subtitle": ImageFont.truetype("DejaVuSans-Bold.ttf", 20),
        }
    except OSError:
        fallback = ImageFont.load_default()
        return {
            "day": fallback,
            "hour": fallback,
            "time": fallback,
            "title": fallback,
            "date": fallback,
            "subtitle": fallback,
        }


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    """Divide texto en varias lineas para ajustarlo al ancho del bloque."""
    if not text:
        return [""]

    words = text.split()
    if not words:
        return [text]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        width = draw.textbbox((0, 0), candidate, font=font)[2]
        if width <= max_width:
            current = candidate
            continue
        lines.append(current)
        current = word
    lines.append(current)
    return lines


def _fit_wrapped_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.ImageFont,
    max_width: int,
    max_height: int,
) -> list[str]:
    """Recorta lineas cuando el alto disponible no alcanza."""
    if not lines:
        return [""]

    sample_bbox = draw.textbbox((0, 0), "Ag", font=font)
    line_height = max(12, sample_bbox[3] - sample_bbox[1] + 2)
    max_lines = max(1, max_height // line_height)
    if len(lines) <= max_lines:
        return lines

    visible = lines[:max_lines]
    last_line = visible[-1]
    while last_line:
        candidate = f"{last_line}..."
        width = draw.textbbox((0, 0), candidate, font=font)[2]
        if width <= max_width:
            visible[-1] = candidate
            return visible
        last_line = last_line[:-1].rstrip()
    visible[-1] = "..."
    return visible


def _draw_centered_multiline_text(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    block: list[int],
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    padding_x: int,
    padding_y: int,
) -> None:
    """Dibuja lineas centradas dentro del bloque respetando padding interno."""
    if not lines:
        return

    sample_bbox = draw.textbbox((0, 0), "Ag", font=font)
    line_height = max(12, sample_bbox[3] - sample_bbox[1] + 2)
    spacing = 2
    text_height = len(lines) * line_height + max(0, len(lines) - 1) * spacing

    usable_top = block[1] + padding_y
    usable_bottom = block[3] - padding_y
    usable_left = block[0] + padding_x
    usable_right = block[2] - padding_x

    start_y = usable_top + max(0, int(((usable_bottom - usable_top) - text_height) / 2))
    for index, line in enumerate(lines):
        line_bbox = draw.textbbox((0, 0), line, font=font)
        line_width = line_bbox[2] - line_bbox[0]
        x = usable_left + max(0, int(((usable_right - usable_left) - line_width) / 2))
        y = start_y + index * (line_height + spacing)
        draw.text((x, y), line, fill=fill, font=font)
