# Informe Final Consolidado De Auditoria Tecnica

Fecha: 2026-04-05

Estado: cierre de auditoria

## 1. Resumen ejecutivo general

La auditoría confirma que el proyecto hoy es un MVP funcional y técnicamente defendible. No es un prototipo desordenado: la refactorización reciente dejó una base clara, con separación real entre orquestación, servicios, persistencia e integraciones.

Hechos observados:

- El sistema opera como un monolito modular por capas, orientado por LangGraph.
- El flujo principal implementado ya cubre onboarding, horario fijo, personalización inicial, prioridades académicas, plan semanal, materialización de instancias y recordatorios.
- La base de datos está bien alineada con ese flujo y soporta versionado y operación durable.
- La deuda principal no está en el diseño general, sino en límites incompletamente cerrados: `AgentState`, lógica aún ubicada en `agents/support/flows`, observabilidad insuficiente, scripts transicionales y seguridad básica mejorable.

Diagnóstico general:

- La arquitectura actual es válida para seguir creciendo como MVP académico.
- No conviene rehacerla ni cambiar de estilo arquitectónico.
- Sí conviene terminar de limpiar límites, endurecer operación y estabilizar infraestructura antes de abrir nuevas features grandes.

## 2. Qué es el proyecto y qué hace hoy realmente

El proyecto es un agente académico conversacional para acompañar estudiantes en:

- onboarding;
- captura de horario académico/laboral y actividades;
- recomendación inicial de métodos de estudio;
- priorización de materias;
- generación de un plan semanal de estudio;
- recordatorios y bases para seguimiento.

Qué hace hoy realmente en código y persistencia:

1. Solicita consentimiento y recolecta el perfil del estudiante.
2. Verifica correo institucional con reto persistido.
3. Persiste al estudiante.
4. Captura y normaliza horario académico y, si aplica, laboral.
5. Captura actividades extracurriculares.
6. Construye un draft, muestra preview, valida conflictos y admite correcciones.
7. Persiste el horario confirmado.
8. Ejecuta el Radar de estudio si el feature flag está activo.
9. Captura prioridades si faltan urgencia o carga por materia.
10. Genera el plan semanal inicial.
11. Persiste priorities y study plan.
12. Materializa instancias fechadas.
13. Siembra políticas y despachos de recordatorio.

Qué no hace todavía en el flujo principal:

- no usa RAG;
- no tiene WhatsApp operativo;
- no integra Telegram;
- no ejecuta sync real con Outlook Calendar o Microsoft To Do dentro del grafo principal;
- no conecta la replanificación al flujo central;
- no activa envío real de correo de onboarding por defecto.

## 3. Mapa estructural del sistema

La estructura actual del repositorio es coherente y suficiente para un MVP robusto.

Mapa estructural principal:

```text
src/
├── agents/support/        # grafo, estado, nodos y flujos conversacionales
├── services/              # casos de uso y lógica de aplicación
├── repositories/          # persistencia PostgreSQL e implementaciones in-memory
├── integrations/          # AI, LangGraph, Microsoft Graph, placeholders de canal
├── schemas/               # contratos compartidos y DTOs
├── bootstrap/             # composition root y settings
├── rag/                   # reservado
└── utils/                 # helpers genéricos

migrations/                # esquema SQL versionado
scripts/                   # utilidades operativas y workers
tests/                     # pruebas funcionales, de arquitectura y persistencia
docs/2026-04-05/          # auditoría actual
```

Archivos más críticos del sistema:

- `langgraph.json`
- `src/agents/support/agent.py`
- `src/agents/support/state.py`
- `src/bootstrap/container.py`
- `src/bootstrap/settings.py`
- `src/services/onboarding/service.py`
- `src/services/personalization/service.py`
- `src/services/planning/study_plan_sync_service.py`
- `src/services/planning/materialization_service.py`
- `src/repositories/planning/repository.py`

Observación:

- El primer corte del repo es técnico por capas y funciona.
- La deuda no está en la estructura top-level, sino en algunas piezas internas demasiado cargadas.

## 4. Arquitectura actual identificada

Arquitectura identificada:

`monolito modular en capas, orientado por grafo, con rasgos hexagonales parciales`

Justificación técnica:

- El runtime real entra por `langgraph.json` y `src/agents/support/agent.py:agent`.
- La orquestación está centralizada en LangGraph y en `AgentState`.
- La lógica principal vive en `src/services/`.
- La persistencia durable vive en `src/repositories/`.
- Las integraciones externas viven en `src/integrations/`.
- El wiring compartido vive en `src/bootstrap/container.py`.

Lo que sí está bien resuelto:

- separación top-level por capas;
- composición explícita del runtime;
- patrón `Protocol + InMemory + Postgres` en varios repositorios;
- encapsulamiento aceptable de Microsoft, LangGraph y AI en infraestructura.

Lo que sigue siendo parcial:

- no es hexagonal estricta;
- parte de la lógica de aplicación sigue en `agents/support/flows`;
- hay fugas de dependencia como `repository -> service` y `integration -> repository`;
- `AgentState` funciona como estado global transversal.

## 5. Flujo actual del agente

El flujo real es turn-based. El agente no corre de principio a fin en un solo paso; ejecuta nodos hasta que necesita nueva entrada del usuario, persiste el estado y se detiene.

Secuencia real principal:

```text
welcome_consent
-> collect_profile
-> send_email_verification
-> verify_email_code
-> confirm_profile
-> persist_profile
-> request_schedules
-> parse_schedules_to_events
-> ask_extracurricular
-> collect_extracurricular_details
-> build_draft_schedule
-> render_schedule_preview
-> validate_schedule
-> apply_schedule_correction (si aplica)
-> persist_schedule
-> collect_study_profile (si está habilitado)
-> collect_study_profile_tiebreaker (si aplica)
-> persist_study_profile
-> collect_priorities (si aplica)
-> build_study_plan
-> END
```

Dependencias del flujo:

- Determinístico:
  - validaciones de onboarding;
  - validaciones de horario;
  - validación del plan;
  - reglas de reminders y materialización.
- Dependiente de LLM:
  - normalización de horarios en texto libre;
  - extracción multimodal parcial;
  - apoyo a parsing de actividades.
- Dependiente de base de datos:
  - onboarding;
  - horarios;
  - personalización persistida;
  - planning;
  - instancias;
  - reminders;
  - checkpointer.
- Dependiente de integraciones externas:
  - Azure/OpenAI u OpenAI;
  - Microsoft Graph;
  - correo real solo si se conecta explícitamente.

Observación consolidada:

- El flujo central del MVP sí existe y sí está implementado.
- Las capacidades futuras visibles en el código aún no forman parte del recorrido principal.

## 6. Estado de modularidad

La modularidad actual es suficiente para seguir creciendo, pero todavía tiene deuda localizada.

Fortalezas:

- `src/services/` es la capa más sana del proyecto.
- `src/repositories/` está bien organizada y favorece testabilidad.
- `src/bootstrap/` es claro y útil.
- `tests/test_refactor_guardrails.py` protege decisiones importantes del refactor.

Debilidades modulares principales:

- `src/agents/support/agent.py` concentra demasiado routing y wiring del grafo.
- `src/agents/support/flows/scheduling/schedule_capture_service.py` y `schedule_review_service.py` son hotspots grandes y multitarea.
- `src/agents/support/flows/planning/persistence_support.py` mezcla orquestación del agente con coordinación de aplicación.
- `src/integrations/microsoft_graph/auth_client.py` concentra demasiadas responsabilidades.
- `scripts/` siguen parcialmente atados a rutas legacy del código previo al refactor.

Dictamen de modularidad:

- suficiente para un MVP;
- mejor que antes del refactor;
- aún no suficientemente limpia para abrir muchas features nuevas sin riesgo.

## 7. Estado de la base de datos y modelo entidad-relación

El modelo de datos actual está bien alineado con el flujo operativo real del agente.

Diagnóstico:

- PostgreSQL es la persistencia principal.
- No se usa ORM; la fuente de verdad del esquema son las migraciones SQL.
- La base combina modelo relacional con snapshots en `JSONB`.
- No existe persistencia vectorial activa ni `pgvector` instalado.

Entidades centrales del negocio:

- `students`
- `schedule_profiles`
- `recurring_schedule_blocks`
- `study_personalization_profiles`
- `study_priority_profiles`
- `study_plan_profiles`
- `study_plan_events`
- `study_plan_event_instances`
- `reminder_policies`
- `reminder_dispatches`

Hallazgos relevantes:

- El core del MVP ya tiene uso real en la base auditada.
- Replanificación, tracking de sesiones, Microsoft sync y checkpointer existen en schema, pero no tenían uso visible en la muestra auditada.
- La mejor entidad del diseño actual es `study_plan_event_instances`.
- La entidad más delicada es `microsoft_graph_connections`, por mezcla de metadata y credenciales sensibles.

Observación:

- El modelo de datos no necesita ser rehecho.
- Sí necesita endurecer seguridad, trazabilidad y clarificar canonicidad de snapshots.

## 8. Principales debilidades

### Observaciones consolidadas

1. `AgentState` está demasiado cargado semánticamente.
2. Parte de la lógica de aplicación sigue en `agents/support`, no en `services/`.
3. Hay hotspots grandes en orquestación y scheduling conversacional.
4. La observabilidad es muy baja: no hay logging estructurado visible.
5. El manejo de errores privilegia fallback funcional, pero pierde capacidad diagnóstica.
6. Hay deuda transicional en scripts operativos.
7. La seguridad básica es mejorable en onboarding y Microsoft Graph.
8. La personalización actual es inicial, no adaptativa.
9. RAG y canales nuevos están reservados, no operativos.
10. Las pruebas son valiosas, pero predominan pruebas con `InMemory*`, `Fake*` y `monkeypatch`, sin CI visible.

### Recomendación asociada

- No atacar estas debilidades con una reescritura.
- Atacarlas con una secuencia de limpieza incremental y con guardrails.

## 9. Riesgos más importantes

### Críticos

1. Crecer sobre un `AgentState` transversal sin cerrar límites.
2. Seguir agregando lógica de aplicación a `agents/support/flows`.
3. Operar el MVP sin observabilidad suficiente.
4. Mantener defaults inseguros y tokens sensibles sin protección adicional.

### Importantes

5. Mantener scripts operativos desalineados con la arquitectura actual.
6. Abrir nuevas integraciones sobre una infraestructura todavía poco observable.
7. Seguir duplicando lógica entre syncs, snapshots y builders sin consolidación mínima.
8. Sobrestimar capacidades aún no activas: RAG, WhatsApp, replanificación integrada, Outlook/To Do en el flujo principal.

### Convenientes

9. Mantener lenguaje de dominio mixto español/inglés.
10. Seguir ampliando el service locator sin controles adicionales.

## 10. Recomendación arquitectónica

### Observación

La arquitectura actual ya es suficientemente buena para este proyecto. Cambiar de estilo arquitectónico sería más costoso que útil.

### Recomendación

Conservar y reforzar esta forma:

`monolito modular por capas, orientado por grafo, con puertos/adaptadores parciales reforzados`

Esto implica:

- mantener `LangGraph` como orquestador del flujo;
- mantener el corte top-level por capas;
- reforzar que `agents/` sea orquestación conversacional;
- mover coordinación de aplicación a `services/`;
- mantener `repositories/` e `integrations/` como fronteras explícitas;
- usar `bootstrap/` como composition root único;
- reservar RAG y canales nuevos como extensiones separadas del core operacional.

Qué conservar:

- estructura actual del repo;
- modelo de persistencia versionada;
- `AppContainer`;
- guardrails de arquitectura;
- organización por dominios dentro de cada capa.

Qué cambiar:

- límites entre `agents` y `services`;
- observabilidad;
- scripts legacy;
- seguridad/configuración;
- trazabilidad técnica y de negocio.

## 11. Roadmap sugerido

### Fase 1. Estabilización estructural sin cambio funcional

- alinear `scripts/` con imports actuales;
- dividir internamente `agent.py` sin cambiar entrypoint;
- introducir logging estructurado mínimo;
- unificar errores públicos por servicio;
- ampliar guardrails;
- agregar CI básico.

### Fase 2. Limpieza de límites entre agente y aplicación

- crear una fachada/pipeline en `services/planning/` para persistencia + materialización + reminders;
- dejar `persistence_support.py` como wrapper fino;
- empezar a mover lógica reutilizable de scheduling a `services/scheduling/`;
- documentar ownership de subestados en `AgentState`.

### Fase 3. Endurecimiento de infraestructura y trazabilidad

- dividir internamente `auth_client.py`;
- endurecer seguridad de tokens Microsoft;
- definir canonicidad entre columnas y `JSONB`;
- vincular `thread_id` con `student_id`;
- agregar pruebas de integración con PostgreSQL real.

### Fase 4. Extensiones controladas

- activar replanificación real cuando el flujo base esté estable;
- incorporar feedback de tracking a personalización;
- abrir `integrations/telegram/` y/o `integrations/whatsapp/` bajo el patrón de senderes;
- implementar RAG solo cuando exista persistencia y contrato separados del core operacional.

## 12. Conclusión general

### Observación final

El proyecto está mejor de lo que sería esperable para un MVP conversacional académico con este alcance. Ya existe una arquitectura defendible, un flujo funcional real y una base de datos coherente con el negocio implementado.

### Recomendación final

No abrir todavía nuevas features grandes sobre la base actual sin antes:

- estabilizar límites entre agente y aplicación;
- mejorar observabilidad y manejo de errores;
- corregir deuda transicional en scripts;
- endurecer seguridad y trazabilidad.

Diagnóstico final:

- El proyecto es viable.
- La arquitectura actual es válida.
- La refactorización reciente fue correcta.
- El siguiente paso no es reinventar la arquitectura, sino terminar de consolidarla antes de seguir creciendo.
