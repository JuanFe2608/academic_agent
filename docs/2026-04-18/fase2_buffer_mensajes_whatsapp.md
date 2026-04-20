# Fase 2 - Buffer De Mensajes Y Agregacion WhatsApp

Fecha: 2026-04-18

## Objetivo

Implementar la capa previa al router para mensajes de WhatsApp:

```text
Webhook WhatsApp -> Buffer -> Payload agregado -> Grafo
```

La fase queda alineada con `docs/2026-04-18/plan_fases_implementacion_mvp_lara.md`,
con el estado operativo de fase 1 y con la politica deterministica de fase 3.

## Alcance Implementado

- DTO `BufferedMessage` en `src/schemas/channels.py`.
- DTO `AggregatedInput` en `src/schemas/channels.py`.
- Servicio in-memory `MessageBuffer` en `src/services/channels/message_buffer.py`.
- Reglas de flush inmediato para:
  - imagen;
  - audio;
  - documento;
  - video;
  - sticker;
  - confirmacion clara;
  - comando critico.
- Timeout configurable.
- Agregacion de texto con saltos de linea.
- Normalizacion ligera de fragmentos.
- Integracion inicial en `WhatsAppChannelService` sin tocar el grafo.
- Puente `aggregated_input_to_human_message` para convertir un payload agregado
  en el `HumanMessage` que consume LangGraph.

## Relacion Con Fase 1

El buffer no escribe directamente en `AgentState`, pero prepara el payload que
debera actualizar despues:

- `last_user_messages`;
- `aggregated_user_text`;
- `noise_turn_count`;
- `confirmation_pending` como senal para flush inmediato sensible.

## Relacion Con Fase 3

`AggregatedInput` incluye `InputClassification`.

Esto permite que los mensajes agregados ya salgan con:

- tipo de input;
- utilidad;
- posible intent;
- senales;
- media types.

El caso de sticker queda clasificado como ruido/no util, por lo que no debe
entrar al grafo como texto academico.

## Decisiones De Arquitectura

- El almacenamiento es in-memory; Redis queda fuera de esta fase.
- La integracion se limita al servicio de canal.
- El grafo principal no se modifica.
- El buffer puede devolver mas de un `AggregatedInput` cuando un comando o
  confirmacion corta una agregacion pendiente.
- Las confirmaciones y comandos criticos no se unen con fragmentos previos.

## Pruebas Relevantes

- `tests/test_whatsapp_message_buffer.py`
- `tests/test_whatsapp_channel_service.py`
- `tests/test_whatsapp_client.py`

Resultado de verificacion:

- `uv run --with pytest python -m pytest tests/test_whatsapp_message_buffer.py tests/test_whatsapp_channel_service.py tests/test_whatsapp_client.py tests/test_input_classification.py tests/test_scope_policy.py tests/test_interaction_state.py`
  -> 38 passed
- `uv run --with pytest python -m pytest`
  -> 437 passed

## Siguiente Paso

Cuando se implemente el webhook final, debe usar:

1. `WhatsAppChannelService.download_inbound()`;
2. `WhatsAppChannelService.buffer_inbound()`;
3. `aggregated_input_to_human_message()` solo cuando exista un `AggregatedInput`
   listo para procesar.
