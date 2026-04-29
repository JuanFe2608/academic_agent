# Analisis y resultados del proyecto

## 1. Alcance del analisis

Este apartado presenta los resultados obtenidos durante el desarrollo del agente academico Lara AI, con enfasis en el cumplimiento de los objetivos especificos, la revision critica de los KPI, los hallazgos tecnicos y practicos, y las brechas pendientes para completar la evaluacion formal del objetivo 4.

El analisis se basa en la evidencia tecnica disponible en el repositorio, especialmente en la arquitectura actual del agente, la implementacion del RAG, el modelo de datos, los documentos de despliegue y el plan de refactorizacion de chatbot a agente autonomo. Tambien incorpora la retroalimentacion cualitativa obtenida en pruebas locales realizadas en el debugger de LangGraph con estudiantes del programa.

Es importante precisar que el proyecto se encuentra desarrollado hasta el objetivo especifico 3. El objetivo especifico 4 esta iniciado, porque ya existen pruebas locales y feedback cualitativo, pero no puede considerarse completamente cerrado hasta realizar el despliegue en Azure, habilitar WhatsApp real o sandbox, validar Microsoft OAuth/Outlook en entorno externo y ejecutar un piloto formal con estudiantes.

## 2. Resultado general del proyecto

El resultado principal del proyecto fue la implementacion de un MVP funcional de agente academico hibrido para estudiantes de Ingenieria de Sistemas y Computacion. El sistema no se limita a responder mensajes como un chatbot tradicional: conserva estado, captura datos del estudiante, organiza horarios, genera planes de estudio, usa una base de conocimiento RAG para recomendar tecnicas y metodos, y opera con herramientas para modificar informacion academica, consultar agenda, replanificar y sincronizar servicios externos.

La arquitectura actual sigue el enfoque definido en `docs/plan_refactorizacion_de_chatbot_a_agente_autonomo.md`: un onboarding estructurado mediante maquina de estados y una fase operativa con agente autonomo basado en ReAct/tool-calling. Esto se evidencia en `src/agents/support/agent.py`, donde el grafo principal fue simplificado a un punto de entrada puro y nodos macro; y en `src/agents/support/nodes/academic_agent/node.py`, donde la fase `running` usa `create_react_agent` con contexto dinamico del estudiante y herramientas.

El proyecto consolido tres resultados tecnicos relevantes:

- Una base de conocimiento RAG especializada en tecnicas y metodos de estudio, con 15 documentos fuente, 468 chunks procesados y 355 relaciones explicitas.
- Una arquitectura modular organizada por capas: `agents`, `services`, `repositories`, `integrations`, `schemas`, `rag` y `bootstrap`.
- Un agente operativo que combina flujos deterministicos para datos sensibles y acciones persistentes, con LLM/RAG para interpretacion, recomendacion y conversacion academica.

## 3. Analisis por objetivo especifico

### 3.1 Objetivo especifico 1: construir un RAG a partir de una base de conocimiento experta

El primer objetivo se cumplio de forma sustancial. El proyecto cuenta con una base de conocimiento especializada ubicada en `knowledge_base/study_recommendations/`, organizada en tecnicas, metodos, marcos conceptuales y matriz de combinacion. El inventario del corpus reporta 15 documentos: 8 tecnicas de estudio, 4 metodos de estudio, 1 marco conceptual, 1 marco de decision y 1 matriz de combinacion.

Las ocho tecnicas caracterizadas son: Pomodoro, recuperacion activa, repeticion espaciada, Feynman, Cornell, mapas conceptuales, interleaving y mnemotecnia. Los cuatro metodos definidos son: metodo de parcial teorico, metodo de lectura y sintesis, metodo de evaluacion numerica breve y metodo de repaso semanal.

El resultado supera una simple recopilacion documental, porque el corpus fue convertido en una estructura consultable por RAG. La implementacion incluye ingestion, normalizacion, chunking, relaciones, retrieval hibrido, reranking, prompting grounded y evaluacion offline. Esto permite que las recomendaciones no dependan solo del conocimiento parametrico del modelo, sino de una base curada y trazable.

Desde el punto de vista academico, esta decision es coherente con la literatura. El uso de RAG fue propuesto por Lewis et al. (2020) para mejorar tareas intensivas en conocimiento mediante recuperacion externa antes de generar respuestas. En el proyecto, este principio se adapto al dominio academico: el agente recupera evidencia del corpus para recomendar tecnicas y metodos segun señales del estudiante, materia, actividad y tiempo disponible.

El contenido del corpus tambien se alinea con hallazgos consolidados de psicologia cognitiva. Dunlosky et al. (2013) identifican la practica de recuperacion y la practica distribuida como tecnicas de alta utilidad. Roediger y Karpicke (2006) muestran que la recuperacion activa mejora la retencion a largo plazo, mientras que Cepeda et al. (2006) respaldan el efecto de la practica distribuida. Esto valida la inclusion de recuperacion activa y repeticion espaciada como tecnicas centrales del sistema.

**Resultado alcanzado:** RAG implementado y conectado como herramienta del agente.

**Evidencia tecnica:** `knowledge_base/study_recommendations/`, `src/rag/`, `src/services/study_recommendations/`, `migrations/0016_rag_study_recommendations.sql`, `scripts/build_rag_corpus.py`, `scripts/evaluate_rag.py`.

**Hallazgo critico:** el KPI original estaba formulado como entrega documental, pero el logro real fue mayor: se construyo un sistema de recuperacion y recomendacion evaluable. Por tanto, el KPI debe medir cobertura, trazabilidad, calidad de recuperacion y utilidad percibida, no solo existencia del documento.

### 3.2 Objetivo especifico 2: disenar la arquitectura del agente y su modelo de datos

El segundo objetivo se cumplio mediante una arquitectura modular orientada a agente. El proyecto paso de una logica conversacional mas cercana a un chatbot de flujos hacia un diseno hibrido: onboarding controlado por maquina de estados y fase operativa con agente ReAct.

La arquitectura actual separa responsabilidades:

- `src/agents/support/`: grafo LangGraph, nodos y adaptacion del estado.
- `src/services/`: reglas de negocio y casos de uso.
- `src/repositories/`: persistencia en PostgreSQL.
- `src/integrations/`: clientes externos para WhatsApp, Microsoft Graph, LLMs y embeddings.
- `src/rag/`: ingestion, retrieval, prompting y evaluacion del RAG.
- `src/schemas/`: contratos compartidos.
- `src/bootstrap/`: configuracion e inyeccion de dependencias.

El modelo de datos tambien evoluciono de forma consistente. Existen migraciones para estudiantes, horarios recurrentes, personalizacion, prioridades, planes de estudio, instancias de sesiones, tracking, replanificacion, recordatorios, Microsoft Graph, OAuth y RAG. Esto demuestra que el agente no depende solo del historial conversacional: persiste entidades academicas reutilizables.

Un hallazgo importante fue la necesidad de reducir complejidad del grafo. El plan de refactorizacion identifico bloqueantes como fases fantasma, nodos demasiado grandes y estado plano con duplicaciones. La implementacion actual corrige parte de estos problemas: existe un nodo `__entry__` puro, un grafo principal reducido y un nodo `academic_agent` que concentra la fase operativa con herramientas.

**Resultado alcanzado:** arquitectura modular implementada, modelo de datos persistente y agente hibrido con herramientas.

**Evidencia tecnica:** `src/agents/support/agent.py`, `src/agents/support/state.py`, `src/agents/support/nodes/academic_agent/`, `src/bootstrap/container.py`, `migrations/`, `docs/plan_refactorizacion_de_chatbot_a_agente_autonomo.md`.

**Hallazgo critico:** el diseno demuestra madurez tecnica, pero aun debe validarse en despliegue real. La arquitectura esta preparada para Azure/WhatsApp, aunque faltan pruebas de infraestructura, observabilidad y seguridad operativa en entorno externo.

### 3.3 Objetivo especifico 3: desarrollar el MVP del agente

El tercer objetivo esta cumplido a nivel local. El MVP implementa las funciones principales definidas en el alcance:

- Gestion de tiempo y agenda mediante captura de horario fijo, actividades academicas y consulta de agenda.
- Planificacion de sesiones de estudio con base en disponibilidad, prioridades y perfil de estudio.
- Recordatorios y seguimiento mediante servicios de reminders, tracking y scripts operativos.
- Replanificacion controlada ante cambios, con propuesta y confirmacion antes de aplicar modificaciones.
- Recomendacion personalizada de tecnicas y metodos de estudio mediante Radar y RAG.
- Integracion con Microsoft Graph para OAuth, Outlook Calendar y Microsoft To Do.
- Canal WhatsApp a nivel de cliente, mapeo de mensajes, buffer, adaptador de canal y sanitizacion de medios.

El cambio mas importante frente al diseno inicial es que la fase operativa ya no depende de un conjunto amplio de handlers aislados. El nodo `academic_agent` recibe el contexto del estudiante y decide que herramienta usar. Entre sus herramientas estan `search_study_methods`, `add_academic_activity`, `edit_academic_activity`, `delete_academic_activity`, `get_pending_activities`, `get_weekly_plan`, `update_study_plan`, `update_priorities`, `get_schedule`, `manage_schedule_change`, `sync_plan_to_calendar` y `sync_tasks_to_todo`.

Esto representa un avance real hacia comportamiento agentivo: si el estudiante dice "tengo parcial de calculo el viernes", el agente puede registrar la actividad, consultar el perfil de estudio, sugerir una tecnica apropiada, revisar el plan y proponer replanificacion.

**Resultado alcanzado:** MVP funcional en entorno local/debugger con integraciones implementadas a nivel de codigo.

**Evidencia tecnica:** `src/agents/support/nodes/academic_agent/tools.py`, `src/services/planning/`, `src/services/reminders/`, `src/services/sync/`, `src/services/channels/`, `src/integrations/whatsapp/`, `src/integrations/microsoft_graph/`.

**Hallazgo critico:** la frase original "MVP con integraciones" es insuficiente como KPI. Debe especificarse si la integracion esta implementada en codigo, probada localmente, validada contra sandbox o validada en produccion/staging. Actualmente el proyecto puede reportarse como "MVP implementado localmente con integraciones listas para validacion externa", no como despliegue productivo terminado.

### 3.4 Objetivo especifico 4: evaluar la calidad del agente

El cuarto objetivo esta parcialmente cumplido. Ya existen pruebas locales en LangGraph debugger y retroalimentacion cualitativa de estudiantes, pero falta el piloto formal en entorno desplegado.

Las pruebas realizadas con Juan Manuel Mendoza y Laura Valentina Vasquez permitieron identificar hallazgos de usabilidad, claridad conversacional y validacion de entradas. Aunque la muestra es pequena, el feedback fue valioso porque detecto problemas reales del flujo antes de desplegarlo:

- Preguntas del Radar con redaccion ambigua o escalas redundantes.
- Respuestas que no siempre coinciden con la pregunta planteada.
- Necesidad de mejorar claridad y longitud de los mensajes.
- Falta de personalizacion del tono, lenguaje y uso de emojis.
- Manejo inadecuado cuando se rechaza la autorizacion de datos.
- Mensaje poco claro cuando la edad esta fuera de rango.
- Dificultad para cambiar el estado del estudiante cuando inicialmente indica que no estudia.
- Confusion sobre el concepto de horario fijo.
- Ausencia de limite razonable para la fecha final del horario.
- Falta de claridad sobre como cambiar una respuesta dentro del flujo.

Estos hallazgos no invalidan el MVP; al contrario, muestran que el sistema ya tiene una base funcional suficientemente avanzada para ser evaluada por usuarios. Sin embargo, tambien muestran que la efectividad no debe medirse solo por ejecucion tecnica. Debe medirse por comprension, tasa de finalizacion, numero de correcciones requeridas, utilidad percibida y capacidad del agente para recuperarse de errores del usuario.

**Resultado alcanzado:** evaluacion local exploratoria con feedback cualitativo.

**Resultado pendiente:** piloto formal con estudiantes, canal WhatsApp, despliegue en Azure, integracion Microsoft real, medicion cuantitativa de KPI y manual de usuario final.

## 4. Analisis critico de KPI

Los KPI iniciales sirven como evidencia de avance, pero varios estan formulados como entregables documentales. Para una seccion de analisis y resultados, conviene diferenciarlos asi:

- Entregable: evidencia de que se produjo algo, por ejemplo un documento, corpus o MVP.
- KPI: medida objetiva o semiobjetiva para evaluar calidad, completitud o efectividad.
- Meta: umbral esperado.
- Instrumento: forma concreta de medicion.

La siguiente matriz propone ajustar los KPI para que sean defendibles en la tesis.

| Objetivo | KPI ajustado | Como se mide | Meta recomendada | Estado actual |
| --- | --- | --- | --- | --- |
| Construir RAG | Cobertura del corpus | Numero de tecnicas, metodos, marcos y matrices documentadas | 8 tecnicas, 4 metodos, minimo 1 marco y 1 matriz | Cumplido: 8 tecnicas, 4 metodos, 2 marcos, 1 matriz |
| Construir RAG | Trazabilidad del conocimiento | Porcentaje de recomendaciones con chunks/fuentes asociadas | >= 95% | Cumplido en evaluacion RAG local documentada |
| Construir RAG | Calidad de recuperacion | Entity recall@k, groundedness rate, violaciones de entidades prohibidas | recall >= 0.90, groundedness = 1.0, violaciones = 0 | Documentado: recall 1.0, groundedness 1.0, violaciones 0 |
| Construir RAG | Adecuacion al perfil | Promedio de utilidad percibida por estudiantes en recomendaciones | >= 4/5 | Pendiente de piloto formal |
| Caracterizar perfil | Completitud del perfil estudiantil | Estudiantes con perfil, horario y Radar completos / estudiantes evaluados | >= 90% | Pendiente con muestra completa |
| Caracterizar perfil | Distribucion de señales de estudio | Reporte de señales frecuentes: procrastinacion, distraccion, olvido, organizacion, etc. | Documento con muestra completa | Pendiente de muestra formal |
| Disenar arquitectura | Trazabilidad de requerimientos | Requerimientos implementados / requerimientos definidos | >= 90% | Parcialmente documentado; falta matriz final |
| Disenar arquitectura | Modularidad arquitectonica | Revision de dependencias entre capas y ausencia de accesos directos indebidos | Sin violaciones criticas | Cumplido conceptualmente; conviene generar reporte final |
| Disenar arquitectura | Cobertura del modelo de datos | Entidades necesarias representadas en migraciones/tablas | 100% dominios MVP | Cumplido en codigo; validar en BD limpia |
| Desarrollar MVP | Cobertura funcional | Escenarios MVP ejecutados correctamente / escenarios definidos | >= 85% en local, >= 80% en piloto | Local avanzado; piloto pendiente |
| Desarrollar MVP | Exito de tareas end-to-end | Usuarios que completan onboarding, horario, Radar y plan / usuarios que inician | >= 80% | Pendiente de medicion formal |
| Desarrollar MVP | Integracion Outlook | Eventos sincronizados correctamente / eventos esperados | >= 95%, duplicados = 0 | Implementado; falta validacion real |
| Desarrollar MVP | Integracion WhatsApp | Mensajes recibidos/enviados correctamente / mensajes de prueba | >= 95% en staging | Implementado en codigo; falta Azure/WhatsApp |
| Desarrollar MVP | Replanificacion efectiva | Cambios aplicados correctamente despues de confirmacion / cambios solicitados | >= 85% | Implementado; falta prueba piloto |
| Evaluar agente | Satisfaccion de usuario | Promedio de encuesta Likert sobre claridad, utilidad, confianza y facilidad | >= 4/5 | Exploratorio positivo, sin muestra suficiente |
| Evaluar agente | Usabilidad | SUS o escala equivalente | SUS >= 68 o utilidad >= 4/5 | Pendiente |
| Evaluar agente | Claridad conversacional | Mensajes comprendidos sin aclaracion / mensajes evaluados | >= 85% | Requiere mejora segun feedback |
| Evaluar agente | Tasa de incidentes conversacionales | Errores, confusiones o bloqueos / sesiones de prueba | <= 15% | Pendiente de medicion formal |
| Evaluar agente | Cierre de hallazgos del piloto | Hallazgos corregidos / hallazgos reportados | >= 80% antes de entrega final | Pendiente |

## 5. Cambios recomendados a los KPI originales

### KPI 1: Caracterizacion del perfil de los estudiantes

El KPI original "Documento con la caracterizacion del perfil con la muestra completa" debe conservarse como entregable, pero no como unico KPI. Se recomienda medir:

- Porcentaje de estudiantes con perfil completo.
- Distribucion de semestre, ocupacion, promedio, disponibilidad y horario fijo.
- Distribucion de resultados del Radar.
- Señales de estudio mas frecuentes.
- Relacion entre señales y tecnicas recomendadas.

**Formula sugerida:** perfiles completos (%) = estudiantes con consentimiento, perfil, horario y Radar completos / total de estudiantes participantes x 100.

### KPI 2: Seleccion de tecnicas y metodos de estudio

El KPI original esta bien como meta minima, pero debe ampliarse. No basta caracterizar 8 tecnicas y 4 metodos; tambien se debe medir si el RAG las recupera correctamente.

**KPI recomendado:** precision de recomendacion por caso de uso.

**Formula sugerida:** casos correctos (%) = recomendaciones que recuperan la tecnica/metodo esperado / total de casos evaluados x 100.

### KPI 3: Definicion de requerimientos

El documento de requerimientos debe complementarse con una matriz de trazabilidad. Cada requerimiento debe asociarse a modulo, archivo, caso de uso y prueba/piloto.

**Formula sugerida:** trazabilidad (%) = requerimientos con evidencia de implementacion / requerimientos definidos x 100.

### KPI 4: Diseno de arquitectura

El documento de arquitectura debe incluir evidencia del cambio de chatbot a agente. El KPI recomendado no debe ser solo "documento con arquitectura", sino "arquitectura implementada y trazable".

**Mediciones sugeridas:**

- Numero de capas implementadas.
- Numero de herramientas disponibles para el agente operativo.
- Existencia de estado persistente por estudiante.
- Existencia de modelo de datos para agenda, plan, tracking, reminders, OAuth y RAG.

### KPI 5: Desarrollo del MVP

"MVP con integraciones" debe dividirse por integracion:

- MVP local funcional.
- Outlook Calendar implementado.
- OAuth Microsoft implementado.
- WhatsApp implementado a nivel de cliente/webhook/adaptador.
- Azure pendiente.
- WhatsApp real/sandbox pendiente.
- Jobs periodicos pendientes de configurar en entorno externo.

**Formula sugerida:** integraciones validadas (%) = integraciones probadas end-to-end / integraciones planeadas x 100.

### KPI 6: Evaluacion del agente

El KPI original debe separarse en evaluacion funcional, evaluacion de usabilidad y evaluacion de calidad de recomendacion.

**KPIs recomendados:**

- Tasa de finalizacion de flujo.
- Utilidad percibida.
- Claridad de mensajes.
- Tasa de replanificacion correcta.
- Tasa de recomendaciones pertinentes.
- Numero de hallazgos criticos corregidos antes de despliegue.

## 6. Analisis del feedback de estudiantes

La retroalimentacion de Juan Manuel Mendoza y Laura Valentina Vasquez muestra que el agente fue percibido como util e intuitivo, pero tambien revela problemas de usabilidad que deben resolverse antes del piloto formal.

| Categoria | Evidencia del feedback | Impacto | Accion recomendada | KPI asociado |
| --- | --- | --- | --- | --- |
| Claridad de redaccion | "Mejorar la redaccion de las respuestas", "partes con mucho texto" | Puede aumentar abandono o respuestas incorrectas | Simplificar mensajes, usar bloques cortos, resaltar instrucciones | Claridad conversacional |
| Preguntas del Radar | P3, P8 y escalas redundantes no cuadran o se explican doble | Afecta calidad del perfil de estudio | Reescribir preguntas y validar consistencia pregunta-respuesta | Completitud/calidad del Radar |
| Consentimiento | Si rechaza datos, no debe reenviar autorizacion | Riesgo etico y legal | Mantener estado de rechazo y explicar limitaciones | Seguridad y privacidad |
| Validacion de edad | Mensaje poco claro fuera de rango | Friccion en onboarding | Mensaje especifico con rango permitido | Tasa de finalizacion |
| Estado del estudiante | Si indica que no estudia, debe poder cambiar el estado | Bloquea recuperacion del usuario | Permitir correccion guiada de ocupacion/estado | Recuperacion ante errores |
| Horario fijo | No se entendio bien el concepto | Puede afectar entrada de agenda | Explicar con ejemplos: clases, trabajo, monitorias, actividades recurrentes | Exito de captura de horario |
| Fecha limite | Permite años no razonables como 2080 | Puede crear planes irreales | Validar fecha dentro de rango academico razonable | Calidad de datos |
| Personalizacion del tono | Solicitan emojis, tono y lenguaje mas ligero | Mejora aceptacion y lectura | Ajustar estilo segun preferencia del estudiante | Satisfaccion |
| Edicion de respuestas | No era claro que debia generar de nuevo el mensaje | Puede confundir en LangGraph/WhatsApp | Agregar instruccion "si quieres cambiar algo, escribeme la correccion" | Recuperacion conversacional |

El hallazgo mas relevante es que los estudiantes no cuestionaron la utilidad general del agente; sus observaciones se centraron en claridad, control de flujo y experiencia conversacional. Esto sugiere que el MVP tiene una propuesta de valor comprensible, pero necesita refinamiento de UX conversacional antes de exponerse a un grupo mayor.

## 7. Impacto tecnico

El impacto tecnico del proyecto se observa en cuatro dimensiones.

Primero, el sistema demuestra que LangGraph puede usarse para combinar flujos estructurados y agente autonomo. El onboarding conserva control deterministico para consentimiento, perfil, horario y Radar, mientras que la fase `running` permite razonamiento con herramientas.

Segundo, el uso de PostgreSQL como base operacional permite mantener continuidad por estudiante. El agente no depende exclusivamente del historial de chat; persiste perfil, horario, actividades, planes, tracking, recordatorios y conexiones Microsoft.

Tercero, el RAG reduce el riesgo de respuestas genericas o inventadas en recomendaciones de estudio. Al usar corpus curado, relaciones y respuestas grounded, el agente puede justificar tecnicas y metodos segun evidencia interna.

Cuarto, la separacion por capas facilita evolucion futura. Las herramientas del agente llaman servicios existentes, no nodos del grafo ni repositorios directamente. Esto disminuye acoplamiento y permite probar dominios por separado.

## 8. Impacto practico

Desde la perspectiva del estudiante, Lara AI ofrece valor practico porque integra procesos que normalmente estan separados: calendario, prioridades, sesiones de estudio, recordatorios, seguimiento y recomendacion de tecnicas.

El impacto esperado es mayor en estudiantes con dificultad para iniciar tareas, distribuir tiempo, recordar contenidos, organizar apuntes o decidir como estudiar segun el tipo de evaluacion. En lugar de entregar una recomendacion generica, el agente usa el perfil del estudiante y el tipo de actividad para sugerir una estrategia.

No obstante, el impacto practico aun debe comprobarse con datos del piloto. Las pruebas locales muestran aceptacion inicial, pero no permiten afirmar mejoras en rendimiento academico. Para sostener esa afirmacion se requeriria una medicion longitudinal con grupo control, notas, cumplimiento de sesiones o cambios en habitos de estudio. Para el alcance del MVP, lo defendible es evaluar utilidad percibida, finalizacion de tareas, pertinencia de recomendaciones y funcionamiento tecnico.

## 9. Comparacion con trabajos relacionados

El proyecto se diferencia de muchos chatbots educativos porque no solo responde preguntas. La revision sistematica de Kuhail et al. (2023) muestra que muchos chatbots educativos siguen rutas predeterminadas, aunque algunos incorporan personalizacion. Lara AI adopta un enfoque intermedio: usa rutas predeterminadas cuando el sistema debe recolectar datos confiables y usa un agente con herramientas cuando el estudiante ya tiene contexto academico registrado.

Frente a sistemas de recomendacion de estudio, el proyecto tambien tiene un rasgo distintivo: no recomienda tecnicas de forma aislada. Integra perfil del estudiante, tipo de materia, actividad, horario, prioridades y disponibilidad. Esta decision es coherente con la literatura de aprendizaje autorregulado, donde la utilidad de una tecnica depende del contexto, del objetivo y de las condiciones del estudiante.

En relacion con RAG, el proyecto sigue la logica de Lewis et al. (2020): recuperar informacion externa relevante antes de generar la respuesta. En este caso, el corpus no es Wikipedia ni una base general, sino una base de conocimiento curada para metodos de estudio aplicables a estudiantes de Ingenieria de Sistemas.

En relacion con tecnicas de aprendizaje, el corpus prioriza estrategias respaldadas por evidencia, como recuperacion activa y practica espaciada, coherentes con Dunlosky et al. (2013), Roediger y Karpicke (2006) y Cepeda et al. (2006). Esto permite argumentar que las recomendaciones del agente no son arbitrarias, sino que se apoyan en principios investigados.

## 10. Pendientes para cerrar el objetivo 4

Para cerrar formalmente el objetivo 4, faltan las siguientes actividades:

1. Desplegar el backend en Azure, preferiblemente en Azure Container Apps.
2. Configurar base de datos PostgreSQL en Azure y aplicar migraciones en ambiente limpio.
3. Configurar secretos en Key Vault o secretos administrados, no en `.env`.
4. Configurar webhook publico de WhatsApp con HTTPS.
5. Validar `WHATSAPP_WEBHOOK_VERIFY_TOKEN` y firma `X-Hub-Signature-256`.
6. Probar envio y recepcion de mensajes WhatsApp con numero real o sandbox.
7. Validar Microsoft OAuth con una cuenta real o tenant de pruebas.
8. Probar sincronizacion de horario y sesiones con Outlook Calendar.
9. Configurar scheduler externo para recordatorios y sesiones perdidas.
10. Definir almacenamiento persistente de medios, idealmente Blob Storage.
11. Conectar logs/auditoria segura sin almacenar texto crudo ni PII innecesaria.
12. Ejecutar piloto con estudiantes y registrar metricas.
13. Corregir hallazgos de feedback antes de entregar la version final.
14. Elaborar manual de usuario con capturas del flujo real.

## 11. Protocolo recomendado para el piloto

Se recomienda ejecutar el piloto en dos etapas.

### Etapa 1: piloto tecnico controlado

Participantes: 2 a 3 usuarios internos.

Objetivo: validar despliegue, WhatsApp, OAuth, Outlook, logs y persistencia.

Escenarios minimos:

- Inicio de conversacion y consentimiento.
- Registro de perfil.
- Captura de horario fijo.
- Radar de estudio.
- Priorizacion.
- Generacion de plan.
- Registro de actividad nueva.
- Consulta de metodo de estudio.
- Replanificacion.
- Sincronizacion con Outlook.

### Etapa 2: piloto academico

Participantes: 5 a 10 estudiantes de Ingenieria de Sistemas y Computacion.

Objetivo: medir utilidad, claridad, tasa de finalizacion y pertinencia de recomendaciones.

Instrumentos:

- Encuesta pretest sobre habitos de organizacion y estudio.
- Lista de tareas funcionales.
- Registro de observaciones por sesion.
- Encuesta postest tipo Likert.
- Preguntas abiertas de feedback.
- Revision de logs sanitizados.

Metricas:

- Tasa de finalizacion del flujo completo.
- Numero promedio de turnos para completar onboarding.
- Numero de aclaraciones solicitadas.
- Errores por usuario.
- Utilidad percibida.
- Claridad percibida.
- Pertinencia de recomendaciones.
- Exito de sincronizacion Outlook.
- Exito de replanificacion.

## 12. Redaccion sugerida de cierre para la tesis

Los resultados obtenidos permiten afirmar que el proyecto alcanzo una implementacion funcional del MVP propuesto hasta el objetivo especifico 3. Se construyo una base de conocimiento RAG especializada, se diseno una arquitectura modular con persistencia y herramientas, y se desarrollo un agente academico capaz de apoyar la gestion del tiempo, la planificacion de estudio y la recomendacion personalizada de metodos.

El principal aporte tecnico fue transformar el sistema desde un flujo conversacional rigido hacia un agente hibrido. Esta arquitectura conserva control deterministico en procesos sensibles, como consentimiento, perfil, horario y acciones externas, pero habilita razonamiento con herramientas en la fase operativa. De esta manera, Lara AI no solo responde mensajes, sino que puede actuar sobre el contexto academico del estudiante.

Los resultados preliminares de evaluacion local muestran una percepcion positiva de utilidad e intuicion conversacional, pero tambien evidencian oportunidades de mejora en redaccion, claridad del Radar, manejo de errores, validaciones y personalizacion del tono. Estos hallazgos son consistentes con el estado del proyecto: el MVP esta tecnicamente avanzado, pero requiere despliegue y piloto formal para validar su efectividad en condiciones reales.

Por tanto, la efectividad del proyecto puede establecerse parcialmente: se demuestra cumplimiento tecnico y funcional del MVP, pero la validacion completa de calidad depende de la ejecucion del objetivo 4 en ambiente desplegado. La siguiente fase debe concentrarse en Azure, WhatsApp, Microsoft Graph, observabilidad y evaluacion con estudiantes, usando los KPI ajustados propuestos en esta seccion.

## 13. Referencias de apoyo

- Lewis, P. et al. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. https://nlp.cs.ucl.ac.uk/publications/2020-05-retrieval-augmented-generation-for-knowledge-intensive-nlp-tasks/
- Dunlosky, J. et al. (2013). Improving Students' Learning With Effective Learning Techniques. https://journals.sagepub.com/doi/abs/10.1177/1529100612453266
- Roediger, H. L. y Karpicke, J. D. (2006). Test-Enhanced Learning: Taking Memory Tests Improves Long-Term Retention. https://journals.sagepub.com/doi/10.1111/j.1467-9280.2006.01693.x
- Cepeda, N. J. et al. (2006). Distributed practice in verbal recall tasks: A review and quantitative synthesis. https://pubmed.ncbi.nlm.nih.gov/16719566/
- Kuhail, M. A. et al. (2023). Interacting with educational chatbots: A systematic review. https://link.springer.com/article/10.1007/s10639-022-11177-3
- LangGraph `create_react_agent` reference. https://reference.langchain.com/python/langgraph.prebuilt/chat_agent_executor/create_react_agent
- Microsoft Graph Calendar API overview. https://learn.microsoft.com/en-us/graph/api/resources/calendar-overview?view=graph-rest-1.0
- Azure Container Apps documentation. https://learn.microsoft.com/azure/container-apps/services
