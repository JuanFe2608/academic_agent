# Fase 19. Apoyo Academico Guiado Y Modo Socratico

Fecha: 2026-04-18

## Objetivo

Permitir que Lara ayude al estudiante a abordar actividades academicas concretas sin resolverlas por completo ni entregar respuestas finales para copiar.

## Politica Implementada

La fase separa tres casos:

- Ayuda permitida: checklist, primeros pasos, descomposicion de consigna y preguntas orientadoras.
- Modo socratico: preguntas acotadas para que el estudiante construya su propio intento.
- Solicitud prohibida: resolver, redactar, solucionar o entregar respuestas finales de quizzes, parciales, talleres, tareas, proyectos, entregas, informes o ejercicios.

El modo socratico queda limitado a tres turnos por ronda. Al llegar al limite, Lara cierra la guia y pide que el estudiante escriba su propio intento antes de continuar con planificacion o revision de agenda.

## Cambios Principales

1. Se agrego `GuidedAcademicSupportResult` y el servicio deterministico `guided_academic_support`.
2. Se implementaron los intents:
   - `request_guided_academic_help`;
   - `enter_socratic_mode`.
3. El servicio extrae contexto minimo:
   - tipo de actividad;
   - materia;
   - tema;
   - objetivo opcional.
4. Si faltan datos, Lara pide solo lo necesario antes de generar guia.
5. Se agrego el nodo fino `guided_academic_support`, que traduce el resultado del servicio al estado LangGraph.
6. El router conversa con este nodo solo cuando no hay un bloque activo que preservar.
7. La politica de alcance rechaza solicitudes directas de solucion y ofrece alternativa guiada.

## Arquitectura

La logica de limites no vive en el grafo. El nodo solo adapta estado:

```text
services/conversation/guided_academic_support.py
  -> agents/support/nodes/guided_academic_support/node.py
  -> agents/support/agent.py
```

Esto evita que `agent.py` siga acumulando reglas conversacionales y mantiene el patron usado en fases anteriores: router y politica en `services/conversation`, coordinacion fina en nodo, estado durable en `interaction`.

## Estado Conversacional

Cuando faltan datos, el flujo guarda:

- `current_domain = guided_academic_support`;
- `interaction_mode = guided` o `socratic`;
- `pending_action = complete_guided_academic_context` o `continue_socratic_mode`;
- `pending_entity_payload` con slots y contador de turnos;
- `missing_fields_json` solo cuando hay datos faltantes.

Cuando se completa una salida permitida, el flujo limpia acciones pendientes y registra `last_allowed_output`, `slots` y `turn_count`.

## Base De Datos

No se agrego migracion. La fase usa el estado conversacional existente y no crea entidades academicas nuevas.

## Pruebas

Pruebas focalizadas ejecutadas:

```bash
uv run --with pytest python -m pytest tests/test_guided_academic_support.py tests/test_input_classification.py tests/test_scope_policy.py tests/test_conversation_router.py
```

Resultado:

```text
42 passed
```

## Criterio De Cierre

- `Ayudame con este taller pero no me lo resuelvas` activa ayuda guiada y pide materia/tema si faltan.
- Una solicitud con contexto completo genera checklist y primera pregunta orientadora.
- `Modo socratico para taller de Calculo sobre derivadas` activa preguntas acotadas.
- `Redacta mi entrega final para copiar` o `Resuelveme este quiz` se rechazan con alternativa guiada.
- El modo socratico no pisa un bloque activo de calendario.
