# Fase 18. Personalizacion de metodo aplicada a actividades

## Objetivo

La fase convierte el resultado del Radar y el RAG de tecnicas/metodos en pasos operativos para una actividad academica concreta: parcial, quiz, taller, tarea, entrega, proyecto, exposicion, lectura o repaso.

## Politica implementada

1. La logica vive en `AppliedStudyMethodService`, no en un nodo del grafo.
2. El servicio recibe tecnica(s) top del Radar, senales/debilidades, materia, tipo de actividad, tiempo disponible, urgencia y dificultad.
3. La recomendacion solo se considera aplicada si la respuesta RAG trae fuentes para el metodo o tecnica seleccionada.
4. Los pasos son breves, verificables y no nombran tecnicas fuera del vocabulario documentado.
5. Si RAG no esta listo o no hay fuentes suficientes, no se inventa una guia aplicada.

## Integracion

- Plan semanal: `build_study_plan` agrega `study_plan.rules.applied_method_guidance` para hasta tres actividades pendientes priorizadas.
- Sesiones: cada guia aplicada guarda `session_event_ids` de las sesiones del mismo subject, para que recordatorios, To Do o replanificacion puedan usar la misma politica despues.
- Respuestas directas: preguntas como "Como estudio para un parcial?" o "Como preparo una exposicion?" se responden con pasos aplicados, no con texto generico sobre una tecnica.
- Router: las preguntas de guia aplicada tienen precedencia sobre CRUD de actividades. "Tengo parcial de calculo manana" sigue siendo registro de actividad; "Como estudio para parcial de calculo?" va a recomendacion.

## Decisiones

No se agrego migracion. La guia queda como metadato operacional en `study_plan.rules`, porque todavia es una proyeccion del plan y no una entidad durable independiente.

No se amplio Microsoft To Do en esta fase. La fase deja `session_event_ids` y pasos aplicados listos para que una siguiente extension decida que checklists se proyectan como tareas sin duplicar la tabla de links.

## Pruebas

Se agregaron pruebas para:

- servicio aplicado con fuentes RAG;
- negativa controlada sin fuentes;
- plan semanal con `applied_method_guidance`;
- ruteo y clasificacion de preguntas aplicadas;
- respuesta directa con pasos accionables.
