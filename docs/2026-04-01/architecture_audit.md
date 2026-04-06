# Auditoría Técnica De Arquitectura

## 1. Resumen Ejecutivo

El repositorio **no necesita una reescritura total**. La base actual ya resuelve parte importante del MVP con una combinación razonable de:

- grafo conversacional con LangGraph,
- estado tipado con Pydantic,
- servicios y repositorios por dominio,
- persistencia PostgreSQL,
- y una suite de pruebas útil para refactorizar con seguridad.

La arquitectura real detectada es la de un **monolito modular orientado por grafo** con una separación parcial `node -> service -> repository`. Esa separación ya existe y es valiosa, pero todavía convive con varios puntos de deuda técnica:

- nodos demasiado grandes que mezclan conversación, reglas de negocio y mutación de estado,
- un módulo `tools/` que hoy funciona como bolsa mixta de infraestructura, helpers y service locator,
- código legado no conectado al grafo principal,
- duplicación de utilidades pequeñas entre nodos,
- placeholders e archivos experimentales que pueden confundir a futuros desarrolladores.

La conclusión principal es:

1. **La dirección general del proyecto es correcta.**
2. **La evolución debe ser incremental y no invasiva.**
3. **La prioridad no es mover carpetas por estética, sino consolidar fronteras arquitectónicas reales.**
4. **El proyecto ya está bien encaminado para crecer hacia OAuth Microsoft, Outlook, To Do, RAG, planificación y WhatsApp, siempre que primero se reduzca el acoplamiento actual.**

## 2. Alcance Auditado

La auditoría cubrió:

- estructura completa del repositorio,
- grafo principal LangGraph,
- contrato de estado,
- nodos de onboarding, captura de horario y personalización,
- servicios y repositorios de onboarding, scheduling y personalization,
- utilidades de LLM, renderer, parser y checkpointer,
- migraciones SQL,
- scripts manuales,
- y la suite de pruebas disponible.

## 3. Arquitectura Actual Detectada

### 3.1 Estilo arquitectónico real

La arquitectura actual puede describirse como:

**Monolito modular con orquestación conversacional en LangGraph y separación parcial por dominios**.

No es una arquitectura hexagonal completa, pero sí tiene varios elementos compatibles con ella:

- **Orquestación** en `src/agents/support/agent.py`.
- **Estado compartido** en `src/agents/support/state.py`.
- **Nodos conversacionales** en `src/agents/support/nodes/`.
- **Dominios funcionales** en:
  - `src/agents/support/onboarding/`
  - `src/agents/support/scheduling/`
  - `src/agents/support/personalization/`
- **Persistencia** vía repositorios con contrato e implementación in-memory/PostgreSQL.
- **Infraestructura** concentrada hoy en `src/agents/support/tools/`.

### 3.2 Capas observadas

#### A. Orquestación conversacional

- `src/agents/support/agent.py`
- `src/agents/support/nodes/*`

Responsabilidad actual:

- enrutar por `phase`,
- detectar nueva entrada,
- construir prompts,
- decidir el siguiente paso del flujo,
- y devolver updates parciales del estado.

#### B. Contrato de estado

- `src/agents/support/state.py`

Responsabilidad actual:

- definir `AgentState`,
- modelar perfil, horario, personalización y estados futuros,
- y además incluir helpers de normalización/validación de eventos.

#### C. Lógica de negocio por dominio

- `onboarding/`: validación de perfil, verificación de email y persistencia de estudiante.
- `scheduling/`: parseo, normalización, conflictos, render y persistencia del horario fijo.
- `personalization/`: cuestionario, scoring determinista, desempate y persistencia del Radar.

#### D. Persistencia e infraestructura

- `repository.py` por dominio.
- `tools/db.py` como service locator global.
- `tools/db_config.py` para resolver conexión.
- `tools/langgraph_checkpointer.py` para persistencia de hilos.
- `tools/llm.py` para acceso a Azure/OpenAI y parsing estructurado.

### 3.3 Hallazgos positivos de la arquitectura actual

Hay varios aciertos reales que conviene conservar:

- **Patrón `service/repository` ya presente** en los tres dominios principales.
- **Scoring de personalización determinista**, alineado con la regla de negocio.
- **Persistencia de threads LangGraph** ya contemplada en PostgreSQL.
- **Suite de pruebas útil** y mejor de lo habitual para un proyecto de grado.
- **Separación de prompts** en múltiples nodos mediante archivos `prompt.py`.
- **Modelos tipados** para bloques, conflictos, resultados y perfiles.

## 4. Flujo Actual Del Sistema

El flujo productivo observado hoy es:

1. `welcome_consent`
2. `collect_profile`
3. `send_email_verification`
4. `verify_email_code`
5. `confirm_profile`
6. `persist_profile`
7. `request_schedules`
8. `parse_schedules_to_events`
9. `ask_extracurricular`
10. `collect_extracurricular_details`
11. `build_draft_schedule`
12. `render_schedule_preview`
13. `validate_schedule`
14. `apply_schedule_correction`
15. `persist_schedule`
16. `collect_study_profile` *(si el módulo está habilitado)*
17. `collect_study_profile_tiebreaker` *(si aplica desempate)*
18. `persist_study_profile`
19. `end`

### 4.1 Onboarding

El onboarding está razonablemente bien modelado:

- captura progresiva del perfil,
- verificación determinista del correo institucional,
- confirmación previa a persistencia,
- y manejo de duplicados en repositorio.

### 4.2 Captura de horario fijo

El flujo de horarios tiene varias capas:

- captura por secciones,
- parseo contextual para pendientes,
- normalización híbrida determinista + apoyo LLM,
- detección de conflictos,
- preview visual,
- y persistencia final.

Esto cubre bien el MVP, pero la lógica quedó muy repartida entre nodos y helpers.

### 4.3 Personalización / Radar de estudio

El módulo de personalización está mejor separado que otras partes:

- pregunta por pregunta,
- parser determinista de respuestas,
- scoring determinista,
- desempate separado,
- persistencia versionada.

Este módulo ya se parece bastante a una buena capa de dominio reutilizable.

## 5. Problemas Encontrados

## 5.1 Acoplamiento arquitectónico

### Problema: `tools/db.py` actúa como service locator global

Efecto:

- oculta dependencias reales de los nodos,
- dificulta inyección explícita por flujo,
- hace más costoso migrar a canales adicionales como web o WhatsApp,
- y mezcla infraestructura con acceso a servicios de negocio.

Impacto: **alto**.

### Problema: `state.py` concentra estado y lógica utilitaria

`src/agents/support/state.py` no solo define modelos del estado conversacional; también contiene:

- normalización de hora,
- normalización de día,
- validación de eventos,
- ordenamiento de eventos.

Efecto:

- mezcla esquema con comportamiento de dominio,
- amplía demasiado la responsabilidad del archivo,
- y vuelve más difícil migrar a `schemas/` y `domain/` en el futuro.

Impacto: **medio-alto**.

### Problema: `tools/llm.py` mezcla demasiadas responsabilidades

El módulo hoy concentra:

- resolución de proveedor Azure/OpenAI,
- prompts para normalización,
- parsing de JSON,
- multimodal con imágenes,
- manejo de errores,
- coerción de payloads.

Efecto:

- frontera difusa entre integración externa y lógica de parsing,
- alto riesgo de crecimiento desordenado cuando entren Outlook, To Do, RAG o WhatsApp,
- difícil reutilización por capacidades.

Impacto: **alto**.

## 5.2 Hotspots de complejidad

Los archivos más grandes y sensibles detectados son:

- `src/agents/support/nodes/apply_modifications/node.py` — 2505 líneas
- `src/agents/support/nodes/request_schedules/node.py` — 641 líneas
- `src/agents/support/tools/schedule_parser.py` — 607 líneas
- `src/agents/support/personalization/questionnaire.py` — 587 líneas
- `src/agents/support/tools/llm.py` — 575 líneas
- `src/agents/support/scheduling/normalizer.py` — 559 líneas
- `src/agents/support/agent.py` — 532 líneas
- `src/agents/support/personalization/scoring.py` — 531 líneas
- `src/agents/support/nodes/collect_extracurricular_details/parsing.py` — 514 líneas
- `src/agents/support/state.py` — 488 líneas

No todos son un problema por sí mismos. Ejemplo: `questionnaire.py` es grande porque contiene datos/configuración. Sin embargo, varios sí muestran mezcla de responsabilidades:

- `request_schedules/node.py`
- `apply_schedule_correction/node.py`
- `collect_extracurricular_details/node.py`
- `tools/llm.py`
- `state.py`

## 5.3 Duplicación de lógica

Duplicaciones observables:

- copia del bloque `onboarding` en múltiples nodos,
- coerción de pendientes en varios nodos y parsers,
- normalización de días y cálculo de siguiente día en varios módulos,
- lógica similar de construcción de prompts para pendientes/correcciones.

Durante esta entrega se eliminó una duplicación segura del bloque de onboarding, pero aún quedan duplicaciones a reducir más adelante.

## 5.4 Código legado o no conectado al camino productivo

### No conectado al grafo principal

- `src/agents/support/nodes/apply_modifications/node.py`
- `src/agents/support/nodes/generate_tentative_extracurricular/node.py`

Ambos siguen teniendo valor como referencia o flujo alterno, pero hoy no forman parte del recorrido principal expuesto por `langgraph.json`.

### Archivos placeholder o experimentales

- `src/auth/microsoft_auth.py`
- `src/agents/support/tools/calendar_google.py`
- `src/agents/support/tools/calendar_outlook.py`
- `main.py`
- `prueba1.py`
- `README.md`
- `INDICATIONS.md`

No deben eliminarse automáticamente sin confirmación funcional, pero sí conviene dejar explícito cuáles son placeholders, PoCs o deuda documental.

## 5.5 Responsabilidad mezclada entre conversación y dominio

Los siguientes nodos tienen demasiada lógica operativa además de la conversación:

- `request_schedules/node.py`
- `apply_schedule_correction/node.py`
- `collect_extracurricular_details/node.py`
- `validate_schedule/node.py`

Estos nodos hoy hacen simultáneamente:

- parsing de intención del usuario,
- coordinación de subflujos,
- mutación detallada del estado,
- composición de prompts,
- y, en algunos casos, decisiones de negocio de scheduling.

Eso vuelve más costoso probar y extender el sistema.

## 5.6 Manejo de errores todavía orientado a entorno de desarrollo

Se observó que algunos errores técnicos se devuelven casi literal al usuario final, por ejemplo durante persistencia o verificación.

Eso es útil durante desarrollo, pero en producción debería separarse en:

- mensaje seguro para usuario,
- detalle técnico para logs/observabilidad.

Impacto: **medio**.

## 5.7 Inconsistencias menores de diseño

- El dominio de código estudiantil tiene parte de la regla hardcodeada en validadores y parte parametrizada en configuración.
- El entrypoint real vive en `langgraph.json`, pero `main.py` queda como placeholder sin papel claro.
- Hay documentos raíz vacíos que reducen claridad de onboarding técnico del repositorio.

## 6. Riesgos Actuales

### Riesgos de corto plazo

- agregar nuevas fases al grafo sin modularizar el routing aumentará fragilidad en `agent.py`,
- crecer en `tools/llm.py` mezclará aún más infraestructura y lógica,
- integrar Microsoft Graph directamente desde nodos aumentará el acoplamiento existente,
- introducir CRUD de actividades sobre el flujo actual sin abstraer scheduling generará más complejidad accidental.

### Riesgos de mediano plazo

- la incorporación de WhatsApp/web puede duplicar lógica conversacional si no se separa el canal del caso de uso,
- el service locator global puede volverse un cuello de botella para pruebas de integración,
- el código legado no conectado puede generar decisiones equivocadas por parte de futuros desarrolladores.

## 7. Código Duplicado / Sin Uso

## 7.1 Duplicación comprobada

- helper de copia de `onboarding` repetido en varios nodos *(ya consolidado en esta entrega)*
- coerción de items pendientes en varios módulos
- funciones auxiliares equivalentes de normalización de día en distintos puntos del scheduling

## 7.2 Código no productivo o de uso incierto

- `src/agents/support/nodes/apply_modifications/node.py` — grande y no conectado al grafo principal
- `src/agents/support/nodes/generate_tentative_extracurricular/node.py` — cubierto por tests/scripts, no por el flujo activo
- `prueba1.py` — PoC manual
- `main.py` — placeholder
- placeholders vacíos/semivacíos de integraciones futuras

## 7.3 Limpieza aplicada en esta entrega

Se limpiaron de forma segura:

- imports no usados,
- variables locales muertas,
- duplicación pequeña del bloque `onboarding`,
- warning de configuración Pydantic legado en `BaseStateModel`.

## 8. Responsabilidades Mal Ubicadas

## 8.1 Donde sí están bien ubicadas

- `onboarding/service.py`, `scheduling/service.py`, `personalization/service.py`
- `repository.py` por dominio
- `formatter.py` en scheduling/personalization
- `langgraph_checkpointer.py`

## 8.2 Donde conviene intervenir luego

### `src/agents/support/state.py`

Debería tender a quedar en dos piezas:

- contrato de estado conversacional,
- utilidades o schemas de evento fuera del estado.

### `src/agents/support/tools/db.py`

Debería migrar hacia:

- factorías de infraestructura explícitas,
- o inyección de dependencias al construir el grafo.

### `src/agents/support/tools/llm.py`

Debería separarse en:

- cliente de proveedor,
- prompts/plantillas de extracción,
- normalizadores de payload,
- capacidades multimodales.

### `src/agents/support/nodes/request_schedules/node.py`

Debería delegar parte de su lógica a un servicio de aplicación del dominio de scheduling, especialmente:

- resolución de ocupación,
- agregado incremental de texto,
- cierre de secciones,
- manejo de pendientes.

## 9. Propuesta De Arquitectura Objetivo

La arquitectura objetivo recomendada para este proyecto es una **arquitectura modular por capas con LangGraph solo como orquestador conversacional**, manteniendo el principio de migración progresiva.

## 9.1 Principios

- **LangGraph** orquesta conversación y estado, no concentra negocio.
- **Servicios** implementan casos de uso puros del dominio.
- **Repositorios** encapsulan SQL y persistencia.
- **Schemas** definen contratos y DTOs.
- **Integrations** encapsulan proveedores externos.
- **RAG** se reserva para conocimiento experto, no para datos operativos.
- **Scheduling operativo** sigue siendo determinista y respaldado por PostgreSQL.

## 9.2 Estructura objetivo sugerida

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

## 9.3 Traducción práctica al repo actual

No recomiendo mover todo ya. La versión incremental sería:

1. mantener `src/agents/support` como capa de compatibilidad,
2. extraer nuevos servicios/casos de uso fuera de `nodes/`,
3. dejar `repository.py` actuales como primera versión de `repositories/`,
4. mover nuevas integraciones a `integrations/` desde el inicio,
5. reservar `rag/` para conocimiento experto de métodos de estudio.

## 10. Plan De Refactorización Progresiva

### Fase 0 — Baseline segura

- documentar arquitectura,
- limpiar imports/variables muertas,
- consolidar helpers repetidos de bajo riesgo,
- mantener comportamiento actual.

### Fase 1 — Endurecer fronteras del grafo

- extraer lógica de scheduling conversacional a servicios de aplicación,
- mantener nodos como coordinadores del turno,
- introducir helpers explícitos de estado por dominio.

### Fase 2 — Separar infraestructura

- partir `tools/llm.py`,
- sustituir gradualmente `tools/db.py` por factorías explícitas,
- crear paquete `integrations/` para nuevos adapters.

### Fase 3 — Preparar crecimiento funcional

- crear módulo de actividades académicas y CRUD,
- crear servicio de planificación semanal,
- crear base para replanificación y notificaciones.

### Fase 4 — Integraciones externas

- Microsoft OAuth2,
- Outlook Calendar,
- Microsoft To Do,
- WhatsApp.

### Fase 5 — RAG especializado

- ingestión de fuentes de métodos de estudio,
- retrieval grounded,
- recomendación explicable,
- sin convertir RAG en fuente primaria del estado operativo.

## 11. Quick Wins

Quick wins identificados durante la auditoría:

- consolidar utilidades pequeñas repetidas,
- limpiar imports no usados,
- documentar placeholders de integraciones futuras,
- remover warning técnico de configuración Pydantic,
- explicitar código legado no conectado al grafo,
- fortalecer documentación del repo.

## 12. Cambios Recomendados Por Prioridad

### Prioridad crítica

- separar nuevas integraciones externas del paquete `tools/` actual,
- evitar meter más lógica de negocio en `request_schedules` y `apply_schedule_correction`,
- definir desde ya que RAG no manejará agenda, tareas ni estados operativos,
- mantener el scoring de personalización 100% determinista.

### Prioridad alta

- reemplazar progresivamente `tools/db.py` por inyección/factorías explícitas,
- dividir `tools/llm.py` por capacidades,
- encapsular mejor los subflujos de scheduling en servicios de aplicación,
- aislar o marcar formalmente el código legado no conectado al flujo principal.

### Prioridad media

- separar utilidades de evento fuera de `state.py`,
- crear un README útil del proyecto,
- mover PoCs y scripts manuales a zonas claramente no productivas,
- agregar observabilidad/logging técnico no expuesto al usuario.

### Prioridad baja

- homogeneizar nombres de paquetes hacia `services/repositories/integrations/schemas`,
- refinar exports y `__init__` vacíos o mínimos,
- seguir completando docstrings en helpers internos de alto valor.

## 13. Veredicto Final

El proyecto está en un punto **saludable para evolucionar**, pero no para crecer sin orden. La arquitectura actual ya tiene la semilla correcta; el siguiente paso no es reescribirla, sino **hacer explícitas sus fronteras**, reducir hotspots y encaminar las integraciones futuras hacia módulos especializados.

La recomendación es continuar con una **refactorización progresiva, reversible y guiada por tests**, manteniendo el grafo actual como fachada de orquestación mientras la lógica de negocio migra gradualmente a capas más limpias.
