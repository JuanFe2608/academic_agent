"""Genera una tabla semanal simple a partir de eventos.

Un renderer es un componente que toma datos y los dibuja en un formato
visual. Aqui se crea una imagen PNG con una tabla de dias y bloques de hora.
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

from agents.support.state import DAY_ORDER, Event, normalize_time, sort_events

COLOR_BY_CATEGORY = {
    "laboral": (255, 200, 200),
    "academico": (200, 255, 200),
    "extracurricular": (200, 220, 255),
    "estudio": (255, 240, 200),
}


def render_week_schedule(
    events: list[Event],
    out_dir: str = "tmp",
    filename: str = "schedule.png",
    start_hour: int = 6,
    end_hour: int = 22,
) -> str:
    """Genera una tabla semanal con eventos y retorna el PNG generado.

    El rango visible por defecto es 06:00 a 22:00. Los eventos que caen fuera
    de este rango se recortan al borde visible o se omiten si quedan fuera.
    """

    os.makedirs(out_dir, exist_ok=True)
    if end_hour <= start_hour:
        raise ValueError("end_hour must be greater than start_hour")
    ordered = sort_events(events)

    days = list(DAY_ORDER)
    hour_count = end_hour - start_hour

    width = 1200
    left_margin = 80
    header_height = 40
    row_height = 45
    height = header_height + hour_count * row_height + 20
    col_width = int((width - left_margin) / len(days))

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    _draw_grid(
        draw,
        days,
        width,
        height,
        left_margin,
        header_height,
        row_height,
        start_hour,
        font,
    )

    for event in ordered:
        _draw_event(
            draw,
            event,
            days,
            left_margin,
            header_height,
            col_width,
            row_height,
            start_hour,
            end_hour,
            font,
        )

    path = os.path.join(out_dir, filename)
    image.save(path, "PNG")
    return path


def _draw_grid(
    draw: ImageDraw.ImageDraw,
    days: list[str],
    width: int,
    height: int,
    left_margin: int,
    header_height: int,
    row_height: int,
    start_hour: int,
    font: ImageFont.ImageFont,
) -> None:
    """Dibuja la tabla base con cabeceras y lineas de hora."""
    draw.rectangle([0, 0, width - 1, height - 1], outline="black")
    for idx, day in enumerate(days):
        x0 = left_margin + idx * int((width - left_margin) / len(days))
        x1 = left_margin + (idx + 1) * int((width - left_margin) / len(days))
        draw.line([x0, 0, x0, height], fill="black")
        draw.text((x0 + 4, 10), day, fill="black", font=font)
        draw.line([x1, 0, x1, height], fill="black")

    hour_count = int((height - header_height - 20) / row_height)
    for hour in range(hour_count + 1):
        y = header_height + hour * row_height
        draw.line([0, y, width, y], fill="black")
        label = f"{start_hour + hour:02d}:00"
        draw.text((5, y + 2), label, fill="black", font=font)


def _draw_event(
    draw: ImageDraw.ImageDraw,
    event: Event,
    days: list[str],
    left_margin: int,
    header_height: int,
    col_width: int,
    row_height: int,
    start_hour: int,
    end_hour: int,
    font: ImageFont.ImageFont,
) -> None:
    """Dibuja un bloque de evento dentro de la tabla semanal."""
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

    y0 = header_height + int(((start_minutes - visible_start) / 60) * row_height)
    y1 = header_height + int(((end_minutes - visible_start) / 60) * row_height)

    color = COLOR_BY_CATEGORY.get(event.get("categoria"), (200, 230, 255))
    draw.rectangle(
        [x0 + 1, y0 + 1, x1 - 1, y1 - 1],
        fill=color,
        outline="blue",
    )
    title = str(event.get("titulo", ""))
    draw.text((x0 + 4, y0 + 4), title, fill="black", font=font)
