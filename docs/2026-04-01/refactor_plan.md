# Plan De Refactorización Progresiva

## 1. Objetivo Del Plan

Definir una ruta de evolución para llevar el repositorio desde su estado actual a una arquitectura más modular y mantenible **sin romper el flujo actual**, preservando:

- onboarding ya funcional,
- captura y validación de horario fijo,
- persistencia PostgreSQL,
- scoring determinista de personalización,
- y compatibilidad progresiva con futuras integraciones.

## 2. Principios Rectores

- **No reescribir todo.**
- **No romper contratos públicos sin motivo fuerte.**
- **Mover lógica antes que mover carpetas.**
- **Mantener LangGraph como orquestador, no como capa de negocio.**
- **Usar PostgreSQL como fuente de verdad operativa.**
- **Usar RAG solo para conocimiento experto y recomendaciones fundamentadas.**
- **Conservar scoring determinista para métodos de estudio.**

## 3. Arquitectura Objetivo Recomendada

## 3.1 Visión

La arquitectura objetivo recomendada es una combinación de:

- **orquestación conversacional** en `agents/`,
- **casos de uso y lógica de dominio** en `services/`,
- **persistencia** en `repositories/`,
- **contratos/schemas** en `schemas/`,
- **adaptadores externos** en `integrations/`,
- **conocimiento experto** en `rag/`.

## 3.2 Estructura sugerida

```text
src/
  agents/
    support/
      agent.py
      state.py
      nodes/
  services/
    onboarding/
    scheduling/
    personalization/
    planning/
    activities/
    notifications/
  repositories/
    onboarding/
    scheduling/
    personalization/
    activities/
  schemas/
    onboarding.py
    scheduling.py
    personalization.py
    activities.py
    planning.py
  integrations/
    azure_openai/
    microsoft_graph/
    whatsapp/
  rag/
    ingestion/
    retrieval/
    prompting/
  utils/
```

## 3.3 Por qué aplica a este proyecto

Porque este proyecto necesita convivir con cinco tipos de cambio muy distintos:

1. evolución del flujo conversacional,
2. crecimiento del dominio académico,
3. consultas y persistencia SQL,
4. integraciones externas con autenticación,
5. recomendaciones basadas en conocimiento experto.

Mezclar esas cinco preocupaciones en nodos LangGraph volvería el sistema muy frágil. Separarlas reduce el riesgo de crecimiento desordenado.

## 4. Estrategia De Migración Sin Romper

## 4.1 Regla práctica

Primero:

- **extraer**,
- luego **envolver**,
- después **redirigir imports**,
- y solo al final **mover archivos** si todavía vale la pena.

## 4.2 Qué NO hacer

- no mover todo `src/agents/support/*` a nuevas carpetas de una sola vez,
- no reescribir el grafo,
- no mezclar Microsoft Graph dentro de nodos existentes,
- no meter RAG en flujos de datos operativos.

## 5. Fases Recomendadas

## Fase 0 — Baseline estabilizada *(aplicable ya)*

Objetivo:

- documentar el estado real,
- limpiar deuda técnica obvia,
- dejar evidencia de arquitectura.

Entregables:

- auditoría,
- mapa técnico,
- plan de refactorización,
- limpieza estática de bajo riesgo.

## Fase 1 — Convertir nodos en coordinadores finos

Objetivo:

- reducir lógica mezclada dentro de nodos grandes.

Acciones:

- crear servicios de aplicación para scheduling conversacional:
  - `schedule_capture_service`
  - `schedule_pending_resolution_service`
  - `schedule_review_service`
- dejar en los nodos solo:
  - lectura del estado,
  - delegación al servicio,
  - escritura del `update` final.

Beneficio:

- pruebas más simples,
- menos acoplamiento entre UX conversacional y negocio.

## Fase 2 — Separar infraestructura actual de `tools/`

Objetivo:

- transformar `tools/` en un espacio más limpio o reducirlo drásticamente.

Acciones:

- mover/adaptar `tools/llm.py` hacia `integrations/azure_openai/` y/o `integrations/openai/`,
- mover adapters de calendario hacia `integrations/microsoft_graph/` y `integrations/google/`,
- convertir `tools/db.py` en factoría explícita temporal o eliminarlo a favor de inyección al construir el grafo.

Beneficio:

- integraciones más claras,
- menos dependencias globales implícitas.

## Fase 3 — Introducir dominio de actividades y planificación

Objetivo:

- soportar el roadmap sin deformar scheduling actual.

Módulos sugeridos:

- `services/activities/activity_service.py`
- `repositories/activities/activity_repository.py`
- `schemas/activity.py`
- `services/planning/study_planning_service.py`
- `services/planning/replan_service.py`

Capacidades esperadas:

- CRUD de actividades académicas,
- priorización,
- ventanas disponibles,
- generación de sesiones de estudio,
- replanificación automática.

## Fase 4 — Integración Microsoft

Objetivo:

- conectar el agente al ecosistema Microsoft sin contaminar la capa conversacional.

Módulos sugeridos:

- `integrations/microsoft_graph/auth_client.py`
- `integrations/microsoft_graph/calendar_client.py`
- `integrations/microsoft_graph/todo_client.py`
- `services/integrations/outlook_sync_service.py`

Reglas:

- OAuth y tokens fuera de los nodos,
- mapeo de eventos y tareas en servicios/adapters,
- persistencia de credenciales con esquema dedicado si aplica.

## Fase 5 — WhatsApp y canales

Objetivo:

- desacoplar el canal del core conversacional.

Módulos sugeridos:

- `integrations/whatsapp/webhook_handler.py`
- `integrations/whatsapp/message_mapper.py`
- `integrations/whatsapp/media_adapter.py`

Regla clave:

- WhatsApp no debe conocer lógica de onboarding o scheduling; solo traducir mensajes hacia/desde el agente.

## Fase 6 — RAG de métodos de estudio

Objetivo:

- incorporar conocimiento experto sin convertirlo en sistema transaccional.

Módulos sugeridos:

- `rag/ingestion/study_methods_ingestor.py`
- `rag/retrieval/study_methods_retriever.py`
- `rag/prompting/study_methods_grounding.py`
- `services/recommendations/study_method_recommendation_service.py`

Regla de diseño obligatoria:

- **RAG responde sobre técnicas, beneficios, contraindicaciones, perfiles y aplicación**,
- **PostgreSQL sigue siendo la fuente de verdad de horario, actividades, tareas y estado operativo**.

## 6. Módulos Que Deberían Crearse Después

## 6.1 Microsoft Auth

Responsabilidad:

- login OAuth2,
- refresco de tokens,
- scopes,
- almacenamiento seguro de credenciales.

Sugerencia:

- `integrations/microsoft_graph/auth_client.py`
- `services/integrations/microsoft_auth_service.py`

## 6.2 Outlook Calendar

Responsabilidad:

- crear/actualizar/eliminar eventos sincronizados,
- mapear bloques internos a eventos externos,
- reconciliar ids externos.

Sugerencia:

- `integrations/microsoft_graph/calendar_client.py`
- `services/integrations/outlook_calendar_sync_service.py`

## 6.3 Microsoft To Do

Responsabilidad:

- crear tareas académicas,
- marcar estados,
- sincronizar vencimientos.

Sugerencia:

- `integrations/microsoft_graph/todo_client.py`
- `services/integrations/todo_sync_service.py`

## 6.4 RAG

Responsabilidad:

- conocimiento experto grounded,
- recuperación contextual por técnica/perfil,
- explicación enriquecida de recomendaciones.

Sugerencia:

- `rag/ingestion/`
- `rag/retrieval/`
- `rag/prompting/`

## 6.5 Planificación

Responsabilidad:

- convertir bloques libres + restricciones + perfil en sesiones de estudio.

Sugerencia:

- `services/planning/study_planning_service.py`
- `schemas/planning.py`

## 6.6 CRUD de actividades

Responsabilidad:

- tareas, entregas, parciales, proyectos, actividades recurrentes y puntuales.

Sugerencia:

- `repositories/activities/`
- `services/activities/`
- `schemas/activity.py`

## 6.7 Notificaciones

Responsabilidad:

- recordatorios,
- seguimiento,
- escalamiento de inactividad,
- avisos de replanificación.

Sugerencia:

- `services/notifications/reminder_service.py`
- `services/notifications/followup_service.py`

## 6.8 WhatsApp

Responsabilidad:

- webhook,
- traducción de payloads,
- media handling,
- idempotencia del canal.

Sugerencia:

- `integrations/whatsapp/`

## 7. Cambios Recomendados Pero Diferidos

Se recomienda **no aplicar aún**, pero sí dejar en backlog priorizado:

- mover archivos de carpeta solo por estética,
- borrar nodos legacy sin confirmar dependencia funcional real,
- introducir una capa de DI completa antes de que haya más de un canal o más de un proveedor externo,
- crear `rag/` hasta tener curación clara de fuentes y casos de uso.

## 8. Riesgos Y Mitigaciones

### Riesgo: romper el grafo actual

Mitigación:

- mantener `agent.py` y nombres de nodos estables mientras se extrae lógica.

### Riesgo: duplicar lógica durante la migración

Mitigación:

- primero extraer helpers/servicios y luego redirigir los nodos.

### Riesgo: acoplar Microsoft Graph directamente al core

Mitigación:

- todo cliente externo entra por `integrations/` y se orquesta desde `services/`.

### Riesgo: usar RAG donde no corresponde

Mitigación:

- documentar explícitamente que horario, tareas y estados operativos no salen de RAG.

## 9. Criterio De Éxito

La migración se considera bien encaminada cuando:

- los nodos más grandes delegan a servicios más pequeños,
- las integraciones externas ya no viven en `tools/` genérico,
- el grafo sigue funcionando sin cambios visibles para el usuario,
- los datos operativos siguen siendo deterministas y persistidos en PostgreSQL,
- y el equipo puede agregar Outlook, To Do, RAG o WhatsApp sin tocar el corazón del onboarding/scheduling actual.

## 10. Próximo Paso Concreto Recomendado

El siguiente paso técnico de mayor valor es:

1. extraer un **servicio de captura/revisión de horarios** desde `request_schedules`, `validate_schedule` y `apply_schedule_correction`,
2. dejar `tools/db.py` solo como compatibilidad temporal,
3. crear desde ya el namespace `integrations/microsoft_graph/` para que la futura autenticación no aterrice dentro de nodos o `tools/`.
