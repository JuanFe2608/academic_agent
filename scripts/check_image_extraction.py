"""Valida extraccion de horarios desde imagen sin usar LangGraph Dev."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from agents.support.tools.llm import (
    get_last_llm_error,
    llm_extract_schedule_from_image,
    llm_extract_text_from_image,
    llm_normalize_schedule,
)
from agents.support.tools.schedule_parser import (
    parse_academic_schedule_text,
    parse_work_schedule_text,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Valida extraccion de horario desde imagen.")
    parser.add_argument("image", help="Ruta local a imagen o data URL")
    parser.add_argument(
        "--hint",
        choices=("academico", "laboral"),
        default="academico",
        help="Tipo esperado de horario",
    )
    parser.add_argument(
        "--timezone",
        default="America/Bogota",
        help="Zona horaria de salida para eventos",
    )
    args = parser.parse_args()

    load_dotenv()
    image_ref = args.image
    if not image_ref.startswith("data:image"):
        image_path = Path(image_ref)
        if not image_path.exists():
            raise SystemExit(f"Imagen no encontrada: {image_ref}")
        image_ref = str(image_path)

    print("== Clasificador multimodal ==")
    extracted = llm_extract_schedule_from_image(image_ref, args.hint)
    print(json.dumps(extracted, ensure_ascii=False, indent=2) if extracted else "None")
    if get_last_llm_error():
        print(f"LLM error: {get_last_llm_error()}")

    print("\n== OCR fallback ==")
    ocr_text = llm_extract_text_from_image(image_ref)
    print((ocr_text[:800] + "...") if ocr_text and len(ocr_text) > 800 else (ocr_text or "None"))
    if get_last_llm_error():
        print(f"LLM error: {get_last_llm_error()}")

    base_text = ""
    if extracted and extracted.get("extracted_text"):
        base_text = str(extracted.get("extracted_text") or "").strip()
    elif ocr_text:
        base_text = ocr_text.strip()

    if not base_text:
        print("\nNo se obtuvo texto para parsear.")
        return

    print("\n== Normalizacion ==")
    normalized = llm_normalize_schedule(base_text, args.hint)
    normalized_text = normalized or base_text
    print(normalized_text)
    if get_last_llm_error():
        print(f"LLM error: {get_last_llm_error()}")

    print("\n== Eventos parseados ==")
    if args.hint == "laboral":
        events = parse_work_schedule_text(normalized_text, args.timezone)
    else:
        events = parse_academic_schedule_text(normalized_text, args.timezone)
    print(f"Total: {len(events)}")
    for event in events:
        print(
            f"- {event.dia} {event.inicio}-{event.fin} | {event.titulo} "
            f"[{event.categoria}/{event.tipo}]"
        )


if __name__ == "__main__":
    main()
