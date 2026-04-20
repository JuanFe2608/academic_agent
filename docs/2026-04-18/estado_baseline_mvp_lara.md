# Estado Baseline Del MVP Conversacional De Lara

Fecha: 2026-04-18

Fase desarrollada: Fase 0 del plan `docs/2026-04-18/plan_fases_implementacion_mvp_lara.md`.

Documento rector: `docs/mvp_academic_agent_lara.md`

## 1. Objetivo De La Fase 0

La Fase 0 congela el comportamiento actual antes de introducir:

- estado conversacional operativo;
- buffer de WhatsApp;
- router hibrido por intents;
- OAuth Microsoft bloqueante;
- extraccion incremental de slots;
- flujo post-Radar.

El objetivo no es activar capacidades nuevas, sino dejar claro que flujo se considera baseline y que pruebas lo protegen.

## 2. Contrato Actual Del Flujo

El flujo activo actual queda asi:

```text
bienvenida
-> consentimiento
-> onboarding con verificacion de correo por codigo
-> confirmacion y persistencia de perfil
-> captura de horario fijo academico/laboral
-> captura de actividades extracurriculares fijas
-> preview, conflictos, correccion, fecha limite
-> persistencia local del horario
-> sync de horario fijo con Outlook si existe conexion Microsoft
-> Radar de estudio si personalizacion esta habilitada
-> cierre en phase=end
```

El flujo post-Radar sigue desactivado automaticamente:

```text
priorities -> end
study_plan -> end
running -> end
```

Esto coincide con `docs/mvp_academic_agent_lara.md`: el proyecto ya tiene nodos y servicios posteriores, pero no se ejecutan automaticamente despues del Radar.

## 3. Matriz De Rutas Baseline

| Ruta baseline | Estado actual esperado | Cobertura principal | Estado |
| --- | --- | --- | --- |
| Primer mensaje del usuario | El agente no interpreta el texto inicial como dato; envia bienvenida, imagen y consentimiento. | `tests/test_out_of_scope_restart.py` | Cubierto |
| Consentimiento aceptado | Marca `consent.accepted=true`, pasa a `phase=profile`. | `tests/test_out_of_scope_restart.py` | Cubierto en Fase 0 |
| Consentimiento rechazado | Marca `consent.accepted=false`, pasa a `phase=end`. | `tests/test_out_of_scope_restart.py` | Cubierto en Fase 0 |
| Reinicio desde fuera de alcance | Si el usuario vuelve a escribir, reinicia bienvenida/consentimiento y limpia estado operativo. | `tests/test_out_of_scope_restart.py`, `tests/test_agent_state_partitioning.py` | Cubierto |
| Nombre invalido | Rechaza numeros y simbolos. | `tests/test_collect_profile_validation.py` | Cubierto |
| Codigo estudiantil valido | Acepta codigo de 8 digitos que inicia por `67` y asigna programa soportado. | `tests/test_collect_profile_validation.py` | Cubierto |
| Codigo estudiantil fuera de alcance | Pide confirmar si pertenece a Ingenieria de Sistemas; si responde no, cierra como out_of_scope. | `tests/test_collect_profile_validation.py` | Cubierto |
| Edad | Validador deterministico entre 15 y 60. | `tests/test_collect_profile_validation.py`, `tests/test_onboarding_services.py` | Cubierto indirectamente |
| Correo valido | Normaliza correo y enruta a verificacion. | `tests/test_collect_profile_validation.py`, `tests/test_onboarding_services.py` | Cubierto |
| Correo invalido | Rechaza dominio/formato no permitido y permanece en `phase=profile`. | `tests/test_collect_profile_validation.py` | Cubierto en Fase 0 |
| Verificacion de correo por codigo | Envia codigo, verifica y vuelve a `phase=profile`. | `tests/test_email_verification_nodes.py`, `tests/test_onboarding_services.py` | Cubierto |
| Confirmacion de perfil | Muestra resumen con programa y correo verificado; permite correccion. | `tests/test_confirm_profile_prompts.py` | Cubierto |
| Persistencia exitosa del perfil | Guarda estudiante y avanza a `phase=schedules`. | `tests/test_collect_profile_validation.py`, `tests/test_onboarding_services.py` | Cubierto en Fase 0 |
| Seleccion solo estudio | Guarda `occupation=solo_estudio` y pide horario academico. | `tests/test_schedule_request_flow.py` | Cubierto |
| Seleccion estudio y trabajo | Pide primero horario academico y luego horario laboral. | `tests/test_schedule_request_flow.py` | Cubierto |
| Ninguna de las anteriores | Cierra flujo porque el MVP requiere que el usuario estudie. | `tests/test_schedule_request_flow.py` | Cubierto |
| Horario academico por texto | Parsea materias, dias y horas; permite agregar mas. | `tests/test_schedule_request_flow.py`, `tests/test_fixed_schedule_pipeline.py` | Cubierto |
| Horario laboral por texto | Parsea dias y rangos laborales, incluso lenguaje natural. | `tests/test_schedule_request_flow.py`, `tests/test_fixed_schedule_pipeline.py` | Cubierto |
| Horario con imagen | Intenta extraccion multimodal en captura de horario; si no puede leer, conserva referencia. | `tests/test_schedule_request_flow.py`, `tests/test_llm_multimodal_parsing.py` | Cubierto |
| Actividades extracurriculares fijas | Captura y parsea actividades fijas no academicas. | `tests/test_extracurricular_flow.py`, `tests/test_extracurricular_parsing.py` | Cubierto |
| Preview sin conflictos | Muestra resumen, imagen y pide confirmacion. | `tests/test_schedule_preview.py`, `tests/test_schedule_draft_service.py` | Cubierto |
| Preview con conflictos | Muestra cruces y permite aceptar o corregir. | `tests/test_schedule_preview.py`, `tests/test_schedule_modifications.py`, `tests/test_schedule_draft_service.py` | Cubierto |
| Conflicto aceptado | Marca `conflicts_accepted=true` y pasa a confirmacion final. | `tests/test_schedule_modifications.py` | Cubierto |
| Correccion de horario | Abre menu por seccion y permite editar nombre, dia, horario o eliminar. | `tests/test_schedule_modifications.py`, `tests/test_schedule_application_services.py` | Cubierto |
| Fecha limite del horario | Pide fecha y pasa a persistencia. | `tests/test_schedule_modifications.py` | Cubierto |
| Persistencia local del horario | Guarda perfil de horario recurrente y pasa a sync. | `tests/test_schedule_persistence.py` | Cubierto |
| Sync Outlook de horario fijo | Sincroniza si hay conexion; si falla, no destruye horario local. | `tests/test_schedule_persistence.py`, `tests/test_outlook_fixed_schedule_sync_service.py` | Cubierto |
| Radar deshabilitado | Despues del sync no activa personalizacion. | `tests/test_personalization_flow.py` | Cubierto |
| Radar habilitado | Despues del sync activa `collect_study_profile`. | `tests/test_personalization_flow.py` | Cubierto |
| Radar sin desempate | Recoge 10 respuestas, calcula perfil, persiste y cierra en `phase=end`. | `tests/test_personalization_flow.py`, `tests/test_personalization_scoring.py` | Cubierto |
| Radar con desempate | Activa 3 retos extra, refina ranking, persiste y cierra. | `tests/test_personalization_flow.py` | Cubierto |
| Post-Radar desactivado | Aunque exista flag historico de prioridades, `persist_study_profile` cierra en `phase=end`. | `tests/test_priorities_flow.py` | Cubierto |
| Rutas de espera del grafo | Si un nodo espera input y no hay input nuevo, rutea a `end`. | `tests/test_agent_wait_routing.py` | Cubierto |

## 4. Capacidades Activas

Estas capacidades forman parte del baseline actual:

- bienvenida e imagen inicial;
- consentimiento de tratamiento de datos;
- onboarding paso a paso;
- validadores deterministicos de perfil;
- verificacion de correo por codigo;
- confirmacion y correccion de perfil;
- persistencia de estudiante;
- captura de ocupacion;
- captura de horario academico;
- captura de horario laboral;
- captura de extras fijos;
- parseo de horarios por texto;
- apoyo multimodal para imagenes de horario;
- preview de horario;
- deteccion y aceptacion/correccion de conflictos;
- fecha limite de horario fijo;
- persistencia de horario fijo;
- sync Outlook de horario fijo;
- Radar de estudio si el modulo de personalizacion esta habilitado;
- desempate del Radar;
- persistencia del perfil de estudio;
- respuesta directa de recomendaciones de estudio mediante RAG cuando llega una consulta en `phase=end`;
- respuesta fuera de alcance generica en `phase=end`;
- renovacion/reparacion de horario fijo si los servicios detectan necesidad.

## 5. Capacidades No Activas Automaticamente

Estas capacidades existen total o parcialmente, pero no deben considerarse activas en el flujo inicial:

- OAuth Microsoft como requisito bloqueante de onboarding.
- Buffer/agregador de mensajes WhatsApp.
- Estado conversacional operativo con intents y slots.
- Router hibrido por dominios.
- Extraccion incremental de slots.
- CRUD conversacional durable de actividades academicas puntuales.
- Priorizacion semanal automatica despues del Radar.
- Construccion automatica del plan semanal despues del Radar.
- Materializacion automatica visible para el usuario despues del Radar.
- Dispatch real de recordatorios por WhatsApp.
- Seguimiento conversacional de sesiones.
- Replanificacion automatica post-Radar.
- Sync de sesiones dinamicas de estudio hacia Outlook.
- Microsoft To Do como proyeccion conversacional.
- Modo socratico completo.
- Politica completa de fuera de alcance, bienestar/crisis y evaluaciones.

## 6. Cambios Realizados En Fase 0

Se agregaron pruebas de caracterizacion para cubrir huecos pequenos del baseline:

1. Aceptacion de consentimiento despues de enviada la bienvenida.
2. Rechazo de consentimiento despues de enviada la bienvenida.
3. Correo institucional invalido en el nodo de onboarding.
4. Persistencia exitosa del perfil y avance a captura de horarios.

Archivos modificados:

- `tests/test_out_of_scope_restart.py`
- `tests/test_collect_profile_validation.py`

No se modifico logica de producto.

## 7. Verificacion Ejecutada

Primero se verifico compilacion de las pruebas modificadas:

```bash
uv run python -m py_compile tests/test_out_of_scope_restart.py tests/test_collect_profile_validation.py
```

Resultado:

```text
OK
```

Tambien se ejecuto un smoke manual de las cuatro pruebas nuevas:

```bash
uv run python -c "import sys; sys.path.append('tests'); import test_out_of_scope_restart as w; import test_collect_profile_validation as c; w.test_welcome_consent_accepts_consent_after_welcome_was_sent(); w.test_welcome_consent_rejects_consent_after_welcome_was_sent(); c.test_collect_profile_rejects_invalid_institutional_email(); c.test_persist_profile_success_moves_to_schedule_capture(); print('manual baseline smoke ok')"
```

Resultado:

```text
manual baseline smoke ok
```

Se ejecuto el subconjunto representativo de Fase 0:

```bash
uv run --with pytest python -m pytest tests/test_out_of_scope_restart.py tests/test_collect_profile_validation.py tests/test_email_verification_nodes.py tests/test_confirm_profile_prompts.py tests/test_schedule_request_flow.py tests/test_fixed_schedule_pipeline.py tests/test_schedule_preview.py tests/test_schedule_modifications.py tests/test_schedule_persistence.py tests/test_personalization_flow.py tests/test_priorities_flow.py tests/test_agent_wait_routing.py
```

Resultado:

```text
99 passed in 17.89s
```

Se ejecuto la suite completa:

```bash
uv run --with pytest python -m pytest
```

Resultado:

```text
408 passed in 96.94s
```

Nota tecnica:

`pytest` no esta declarado en `pyproject.toml` dentro de las dependencias de desarrollo. Por eso se uso `uv run --with pytest`. Si se quiere que el comando normal `uv run python -m pytest` funcione sin `--with`, conviene agregar `pytest` al grupo `dev` en una fase de higiene de tooling.

## 8. Contrato Que No Deben Romper Las Fases Siguientes

Las siguientes fases deben preservar estas garantias:

1. El primer mensaje nunca se interpreta como dato de onboarding antes de enviar bienvenida y consentimiento.
2. Sin consentimiento aceptado no se capturan datos personales.
3. El onboarding actual debe seguir funcionando si OAuth bloqueante esta desactivado por flag.
4. La verificacion por codigo debe seguir funcionando hasta que OAuth tenga subflujo completo.
5. La captura de horarios debe seguir aceptando texto normal y mensajes multilinea.
6. La imagen de horario solo debe tener efecto util dentro de captura de horario.
7. Los conflictos de horario no deben bloquear si el usuario los acepta conscientemente.
8. El horario local no debe perderse si falla Outlook.
9. El Radar debe poder cerrar en `phase=end` sin disparar prioridades automaticamente mientras post-Radar este desactivado.
10. Las rutas `priorities`, `study_plan` y `running` no deben activarse automaticamente hasta la fase correspondiente.
11. Los nodos no deben importar repositorios ni integraciones directamente.
12. `AgentState` no debe absorber logica de negocio nueva.

## 9. Estado De Cierre De La Fase 0

La Fase 0 queda desarrollada.

Criterios:

- Matriz del flujo actual creada.
- Cobertura existente revisada.
- Huecos criticos pequenos cubiertos con pruebas.
- Diferencia entre MVP activo y MVP objetivo documentada.
- Subconjunto representativo verificado.
- Suite completa verificada.

Resultado final:

```text
Baseline protegido: 408 pruebas pasando.
```
