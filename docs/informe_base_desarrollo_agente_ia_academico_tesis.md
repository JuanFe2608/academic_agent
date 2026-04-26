# Informe base para la redaccion del desarrollo del agente de IA academico

## 1. Proposito de este documento

El presente documento se elaboro como insumo base para la redaccion del capitulo de desarrollo del trabajo de grado sobre el agente de IA academico Lara. Su objetivo fue consolidar, en una sola narrativa formal, la evolucion del sistema desde su planteamiento inicial hasta su estado de madurez funcional, incluyendo las decisiones de arquitectura, los modulos implementados, las integraciones realizadas, los problemas tecnicos encontrados, las refactorizaciones ejecutadas, la implementacion del canal de WhatsApp y los criterios de validacion aplicados.

El texto se redacto en pasado, con enfoque academico y tecnico, de modo que pudiera reutilizarse para construir secciones de tesis tales como planteamiento del sistema, metodologia de implementacion, arquitectura del software, integraciones, despliegue, resultados de ingenieria, dificultades encontradas, validacion y trabajo futuro.

### Imagen recomendada para esta seccion

- Una figura sencilla tipo portada interna del capitulo, con el titulo "Desarrollo del agente de IA academico Lara" y un diagrama general del sistema.
- Si no se desea crear una imagen nueva, puede usarse una captura del documento [docs/arquitectura_big_picture.md](/home/jfjaramillo12/TESIS/academic_agentAI/docs/arquitectura_big_picture.md) convertida en diagrama formal.

## 2. Contexto general del proyecto

El proyecto se desarrollo como un MVP de agente academico orientado exclusivamente a cinco capacidades funcionales:

1. gestion del tiempo y la agenda academica;
2. planificacion de sesiones de estudio con base en metodos de estudio;
3. recordatorios y seguimiento;
4. replanificacion automatica ante cambios;
5. recomendacion personalizada de metodos de estudio.

Desde el inicio se delimito el alcance para evitar convertir el sistema en un asistente generalista. En consecuencia, el agente se especializo en apoyar a estudiantes universitarios en tareas concretas de organizacion academica y no en resolver consultas amplias de tipo emocional, medico, legal o fuera del dominio academico. Esta restriccion fue una decision de diseño clave, porque permitio concentrar la arquitectura, el modelo conversacional y la persistencia de datos en un caso de uso bien definido y medible.

El sistema se concibio para operar mediante conversacion por WhatsApp, con soporte de backend en Python, orquestacion con LangGraph, persistencia en PostgreSQL e integraciones con Microsoft Graph para calendario, correo, OAuth y, de manera proyectada o parcial segun la fase, Microsoft To Do.

### Imagen recomendada para esta seccion

- Una figura de alcance funcional del MVP con cinco bloques: agenda, planificacion, recordatorios, replanificacion y recomendacion personalizada.
- Tambien sirve una infografia sencilla que muestre al estudiante en WhatsApp y las cinco capacidades alrededor.

## 3. Problema que dio origen al desarrollo

El desarrollo del agente surgio de una necesidad concreta: los estudiantes suelen enfrentar sobrecarga academica, multiplicidad de entregas, dificultad para organizar horarios, mala distribucion del tiempo de estudio y uso ineficiente de tecnicas de aprendizaje. Aunque existen calendarios, gestores de tareas y asistentes genericos, la mayoria no integra en un mismo flujo:

- captura estructurada del contexto del estudiante;
- comprension del horario real del usuario;
- planificacion academica adaptada a prioridades;
- seguimiento de sesiones de estudio;
- replanificacion ante eventos nuevos;
- recomendacion personalizada de metodos de estudio.

El problema, por tanto, no era solamente responder mensajes, sino desarrollar un agente academico con contexto persistente, reglas operativas claras y capacidad para convertir conversacion en acciones concretas sobre el plan academico del estudiante.

### Imagen recomendada para esta seccion

- Una figura de "problema actual vs solucion propuesta".
- Lado izquierdo: estudiante con tareas, parciales y desorden.
- Lado derecho: agente Lara organizando horario, sesiones y recordatorios.

## 4. Objetivo de ingenieria del sistema

Desde el punto de vista tecnico, el objetivo consistio en construir un agente conversacional con memoria operativa y persistencia durable, capaz de:

- registrar el perfil del estudiante;
- capturar y validar su horario fijo academico, laboral y extracurricular;
- modelar un perfil de estudio personalizado;
- detectar prioridades academicas;
- generar un plan de estudio semanal;
- sincronizar elementos del plan con servicios externos;
- responder consultas especializadas sobre tecnicas y metodos de estudio mediante RAG;
- registrar cambios academicos y replanificar cuando fuera necesario.

Este objetivo fue mas exigente que el de un asistente conversacional basico, porque requirio combinar elementos deterministas, logica de negocio, integraciones externas, persistencia de estado conversacional y uso controlado de IA generativa.

### Imagen recomendada para esta seccion

- Un diagrama de objetivos del sistema en forma de mapa conceptual.
- Tambien puede usarse una tabla con dos columnas: "objetivo funcional" y "capacidad implementada".

## 5. Enfoque metodologico de desarrollo

El desarrollo se realizo de forma incremental y por fases. En lugar de intentar construir desde el inicio una autonomia plena en todos los procesos, se adopto un enfoque de maduracion progresiva:

1. primero se construyo un flujo conversacional guiado y determinista para asegurar consistencia en onboarding y captura de datos;
2. despues se separaron capas de negocio, persistencia e integraciones;
3. posteriormente se incorporaron modulos especializados como personalizacion, planificacion, sincronizacion y RAG;
4. finalmente se ejecuto una refactorizacion orientada a fortalecer al agente como sistema autonomo con mejor separacion de responsabilidades y mayor capacidad de composicion.

Este enfoque fue adecuado porque permitio estabilizar primero las funciones criticas del MVP y dejar la fase de autonomia operacional para un momento en el que ya existian datos persistidos, servicios reutilizables y una base arquitectonica suficientemente madura.

### Imagen recomendada para esta seccion

- Una linea de tiempo de desarrollo por fases.
- Puede construirse con los documentos de `docs/2026-04-03/`, `docs/2026-04-06/`, `docs/2026-04-17/` y `docs/2026-04-18/`.

## 6. Seleccion del stack tecnologico

La seleccion tecnologica respondio a criterios de compatibilidad, velocidad de implementacion y capacidad de evolucion:

- Python 3.11+ se utilizo como lenguaje principal por su ecosistema para IA, APIs y procesamiento de datos.
- LangGraph se eligio como orquestador del flujo conversacional por su capacidad para modelar estados, nodos, transiciones y checkpointing.
- PostgreSQL se utilizo como base de datos por su robustez transaccional, flexibilidad para datos estructurados y soporte posterior para `pgvector`.
- FastAPI se empleo para exponer el backend y recibir webhooks.
- Microsoft Graph se integro para OAuth, sincronizacion con Outlook Calendar, correo y servicios relacionados.
- WhatsApp Cloud API se adopto como canal de interaccion con el estudiante.
- OpenAI o Azure OpenAI se utilizaron para tareas de clasificacion, extraccion estructurada, asistencia multimodal, embeddings y generacion de respuestas acotadas.

La combinacion de estas tecnologias permitio un equilibrio entre control ingenieril y uso selectivo de modelos de lenguaje.

### Imagen recomendada para esta seccion

- Una tabla de stack tecnologico por capa: backend, orquestacion, base de datos, IA, canal, despliegue.
- Tambien puede ser un diagrama por logos si la tesis permite iconografia.

## 7. Concepcion del agente academico desde su inicio

Desde su planteamiento inicial, Lara se concibio como un agente academico y no como un sistema de respuesta abierta. El rasgo distintivo del proyecto no fue simplemente conversar con el estudiante, sino operar sobre informacion estructurada del usuario para producir acciones concretas dentro de su contexto academico.

Por esta razon, incluso en las primeras etapas de implementacion, el sistema se diseno con componentes propios de un agente:

- estado persistente por estudiante;
- fases operativas;
- flujos guiados para recoleccion de contexto;
- servicios de negocio separados de la capa conversacional;
- integraciones con sistemas externos;
- capacidad de producir salidas accionables como agenda, sincronizacion, plan de estudio y recomendaciones especializadas.

La evolucion del proyecto no consistio en pasar de una idea simple de conversacion a un cambio de naturaleza del sistema, sino en refinar progresivamente una arquitectura de agente que al comienzo operaba con mayor guiado estructural y posteriormente fue acercandose a una autonomia mas amplia en la fase operacional.

### Imagen recomendada para esta seccion

- Un diagrama conceptual de "que hace a Lara un agente academico".
- Puede tener tres capas: contexto del estudiante, razonamiento operativo, acciones sobre agenda y estudio.

## 8. Arquitectura general del sistema

La arquitectura final se estructuro como un monolito modular orientado por grafo, con organizacion por capas y composition root explicito. La regla de dependencia se definio asi:

`agents -> services -> repositories/integrations -> schemas/utils`

Esta decision fue central para evitar que la logica conversacional se mezclara con persistencia o integraciones externas.

Las capas principales quedaron asi:

- `src/api/`: endpoints HTTP y manejo de webhooks.
- `src/api/agent_runner.py`: puente entre WhatsApp y el grafo del agente.
- `src/agents/support/`: grafo LangGraph, nodos, flujos conversacionales y adaptacion del estado.
- `src/services/`: reglas de negocio y casos de uso reutilizables.
- `src/repositories/`: persistencia durable en PostgreSQL.
- `src/integrations/`: clientes para servicios externos como Microsoft Graph, WhatsApp, LLMs y embeddings.
- `src/schemas/`: contratos, DTOs y modelos compartidos.
- `src/bootstrap/container.py`: composition root para wiring de servicios.

En terminos de ejecucion, un mensaje entrante de WhatsApp era recibido por FastAPI, transformado en un `HumanMessage`, enviado al grafo LangGraph, procesado segun el estado persistido del estudiante, y finalmente convertido de nuevo en mensajes salientes hacia WhatsApp.

### Imagen recomendada para esta seccion

- La mejor imagen para este bloque es un diagrama de arquitectura por capas.
- Puede construirse a partir de [docs/arquitectura_big_picture.md](/home/jfjaramillo12/TESIS/academic_agentAI/docs/arquitectura_big_picture.md).
- Tambien sirve un pantallazo del arbol `src/` resaltando `api`, `agents`, `services`, `repositories`, `integrations` y `schemas`.

## 9. Construccion del flujo operacional del agente

### 9.1 Bienvenida y consentimiento

El primer bloque funcional desarrollado fue la recepcion controlada del usuario. El agente no interpreto el primer mensaje del estudiante como dato de onboarding. Antes de capturar informacion personal, se envio un mensaje de bienvenida y una solicitud de autorizacion para el tratamiento de datos personales.

Esta decision cumplio tres objetivos:

- mantener consistencia legal y etica en el tratamiento de datos;
- evitar que el sistema asumiera informacion valida sin consentimiento;
- establecer una frontera conversacional clara desde el primer turno.

### Imagen recomendada para esta subseccion

- Un pantallazo real del mensaje de bienvenida en WhatsApp.
- Si existe imagen de saludo en `assets/whatsapp/`, conviene incluirla junto con una captura del texto de consentimiento.

### 9.2 Onboarding del estudiante

Despues del consentimiento, se desarrollo un onboarding secuencial para capturar:

- nombre completo;
- codigo estudiantil;
- edad;
- correo;
- datos academicos adicionales como semestre y promedio;
- validaciones de pertenencia al programa objetivo.

La validacion fue principalmente determinista. Esto redujo errores y evito que el modelo generativo inventara o transformara datos de identidad sensibles. En fases intermedias se uso verificacion de correo por codigo. Posteriormente, el diseño evoluciono hacia un esquema en el que la autorizacion OAuth con Microsoft se convirtio en un punto de control mas alineado con las necesidades del MVP.

### Imagen recomendada para esta subseccion

- Un diagrama de flujo del onboarding.
- Tambien puede usarse una secuencia de capturas de WhatsApp mostrando nombre, codigo, correo y confirmacion de perfil.

### 9.3 Captura de horario

El horario fijo fue uno de los dominios mas complejos. El sistema tuvo que admitir:

- bloques academicos;
- bloques laborales;
- actividades extracurriculares fijas;
- entradas en texto libre;
- en algunos casos, apoyo multimodal mediante imagenes de horarios.

El flujo no se limito a almacenar texto. Se desarrollaron servicios para:

- parsear horarios;
- convertir entradas en eventos estructurados;
- detectar cruces y conflictos;
- construir un borrador de horario;
- mostrar una vista previa;
- permitir correcciones por seccion;
- persistir el horario validado;
- proyectarlo hacia Outlook cuando existia conexion con Microsoft.

Este bloque fue especialmente importante porque se convirtio en la base operativa del resto del agente. Sin horario fiable, no era posible planificar sesiones de estudio realistas ni detectar espacios disponibles para replanificacion.

### Imagen recomendada para esta subseccion

- Un ejemplo de horario ingresado por el usuario y su transformacion a bloques estructurados.
- Un pantallazo del preview del horario.
- Si no existe una buena captura, conviene crear una figura propia con "entrada en lenguaje natural -> parser -> horario estructurado".

## 10. Modelado del estado conversacional y persistencia del contexto

Uno de los componentes nucleares del desarrollo fue el estado del agente. Al inicio, el sistema crecio alrededor de un `AgentState` cada vez mas amplio, que concentraba mensajes, fase actual, datos del estudiante, horario, perfil de estudio, prioridades, calendario y otros elementos operativos.

Con el avance del proyecto, este modelo presento tensiones de crecimiento. La solucion adoptada no fue una reescritura total, sino una refactorizacion progresiva del estado en particiones tipadas por dominio:

- estado conversacional;
- estado de onboarding;
- estado de scheduling;
- estado de planning;
- estado de integraciones;
- estado de interaccion.

Este rediseño permitio dos mejoras:

1. mantener compatibilidad con LangGraph y con el contrato plano existente;
2. reducir el acoplamiento conceptual del sistema y preparar el camino para una operacion mas autonoma del agente.

La experiencia del proyecto mostro que en sistemas conversacionales con memoria, el estado es simultaneamente un activo y un riesgo: es indispensable para continuidad, pero si crece sin fronteras claras termina convirtiendose en un foco de deuda tecnica.

### Imagen recomendada para esta seccion

- Un diagrama del `AgentState` dividido por particiones.
- Tambien sirve un fragmento del archivo [src/agents/support/state.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/state.py) resumido visualmente en una figura.

## 11. Desarrollo de modulos de negocio

### 11.1 Modulo de onboarding

Se implementaron validadores, mensajes guiados, confirmacion de perfil y persistencia de estudiante. El objetivo fue garantizar que la informacion minima quedara consistente antes de continuar con procesos posteriores.

### Imagen recomendada para esta subseccion

- Pantallazo de mensajes de validacion o confirmacion de perfil.

### 11.2 Modulo de scheduling

Este modulo incluyo captura, parsing, correccion, validacion y persistencia del horario fijo. Se implementaron servicios de apoyo para deteccion de conflictos, gestion de bloques y sincronizacion de horario con Outlook.

### Imagen recomendada para esta subseccion

- Diagrama del pipeline de scheduling.
- Pantallazo de un caso de conflicto y su correccion.

### 11.3 Modulo de personalizacion

El sistema incorporo un Radar de estudio para identificar afinidades o preferencias de tecnicas de aprendizaje. Este modulo no se resolvio como una recomendacion generativa libre, sino como una combinacion de cuestionario, scoring determinista y desempate en caso de resultados cercanos. Con ello se construyo un perfil de estudio utilizable por el planificador y por el modulo de recomendaciones.

### Imagen recomendada para esta subseccion

- Un esquema del Radar de estudio con entradas, scoring y resultado final.
- Si existe una salida textual del perfil, puede mostrarse en una captura.

### 11.4 Modulo de prioridades

Se desarrollo la base para capturar y procesar prioridades academicas semanales. Aunque parte de esta funcionalidad quedo en etapas de activacion controlada durante varias fases del proyecto, su diseño respondio a la necesidad de traducir actividades y exigencias del estudiante en una jerarquia operativa.

### Imagen recomendada para esta subseccion

- Una tabla o ranking de prioridades semanales.
- Tambien puede crearse una imagen tipo backlog priorizado por urgencia e importancia.

### 11.5 Modulo de planificacion de estudio

Sobre la base del horario, las prioridades y el perfil de estudio, se implemento un modulo para construir planes semanales de estudio. Este modulo contemplaba persistencia, enriquecimiento pedagogico, materializacion de sesiones y soporte para seguimiento posterior.

### Imagen recomendada para esta subseccion

- Un ejemplo de plan semanal de estudio generado.
- Muy util una tabla de lunes a domingo con bloques asignados.

### 11.6 Modulo de seguimiento y recordatorios

Se implementaron estructuras y servicios para politicas de recordatorio, seguimiento de sesiones y registro de cumplimiento. Este componente fue importante porque traslado al agente desde una funcion meramente consultiva hacia una funcion de acompanamiento operativo.

### Imagen recomendada para esta subseccion

- Pantallazo de un recordatorio por WhatsApp.
- Un diagrama simple de "sesion programada -> recordatorio -> confirmacion -> tracking".

### 11.7 Modulo de replanificacion

El proyecto desarrollo mecanismos para que nuevas actividades, cambios en el contexto o conflictos de tiempo provocaran una reorganizacion controlada del plan. Esta capacidad fue una de las piezas que justificaron la madurez del agente.

### Imagen recomendada para esta subseccion

- Figura comparativa "plan original vs plan replanificado".
- Tambien puede ser un diagrama de decision para replanificacion.

### 11.8 Modulo de recomendaciones de estudio

El sistema incorporo un servicio especializado para recomendaciones de tecnicas y metodos de estudio. Este modulo se apoyo en RAG para responder con base en un corpus interno curado y no solo mediante conocimiento general del modelo.

### Imagen recomendada para esta subseccion

- Un diagrama de RAG simplificado.
- Una captura de una recomendacion respondida al usuario con menciones de tecnica, metodo y justificacion.

## 12. Implementacion de WhatsApp como canal principal del agente

La implementacion de WhatsApp constituyo una parte central del desarrollo, debido a que el agente se concibio para operar sobre un canal de uso cotidiano para el estudiante. La solucion no se limito a "enviar y recibir mensajes", sino que se construyo como un pipeline productivo completo entre Meta WhatsApp Cloud API, FastAPI, LangGraph y el servicio de salida al canal.

### 12.1 Punto de entrada HTTP del sistema

Se implemento [src/api/app.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/api/app.py) como servidor FastAPI con cuatro endpoints principales:

- `GET /health` para probes de disponibilidad, especialmente utiles en Azure;
- `GET /webhook` para la verificacion del handshake de WhatsApp Cloud API mediante `hub.verify_token`;
- `POST /webhook` para la recepcion de mensajes entrantes y su despacho al agente en segundo plano;
- `GET /oauth/callback` para completar el flujo OAuth de Microsoft y devolver una pagina HTML al estudiante.

Esta capa permitio separar claramente la frontera de red del resto del sistema y preparar el agente para despliegue real.

### Imagen recomendada para esta subseccion

- Captura del archivo `src/api/app.py` mostrando los cuatro endpoints.
- Mejor aun, un diagrama de cajas con `health`, `webhook`, `oauth/callback`.

### 12.2 Pipeline de procesamiento del mensaje entrante

Se implemento [src/api/agent_runner.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/api/agent_runner.py) como pipeline completo entre WhatsApp y el agente. Este componente se encargo de:

- construir el agente desde variables de entorno mediante `AgentRunner.from_env()`;
- ejecutar el agente en un `ThreadPoolExecutor` para no bloquear el event loop de FastAPI;
- construir el `HumanMessage` a partir de texto, imagenes u otros medios;
- extraer unicamente las respuestas nuevas del turno actual mediante `_extract_new_ai_messages()`;
- manejar errores y emitir un mensaje fallback al estudiante.

En la practica, este componente fue la pieza que conecto el mundo externo del canal con el runtime conversacional interno del agente.

### Imagen recomendada para esta subseccion

- Un diagrama secuencial del pipeline `WhatsApp -> FastAPI -> AgentRunner -> LangGraph -> WhatsApp`.
- Tambien sirve un fragmento del codigo de `AgentRunner` resaltando los metodos clave.

### 12.3 Flujo de produccion del canal WhatsApp

El flujo operacional implementado fue el siguiente:

`WhatsApp Cloud API -> POST /webhook
-> extract_inbound_messages()
-> background_task: AgentRunner.process_message()
-> run_in_executor (thread pool)
-> agent.invoke({"messages": [HumanMessage]}, config={"thread_id": phone_number})
-> PostgresLangGraphCheckpointer
-> _extract_new_ai_messages()
-> WhatsAppChannelService.send_agent_messages()`

Este diseno fue importante porque permitio:

- aislar el ingreso del mensaje del procesamiento interno;
- mantener el estado del estudiante por `thread_id`;
- tolerar pausas entre mensajes;
- soportar interacciones multimodales;
- responder en un canal real de uso diario.

### Imagen recomendada para esta subseccion

- Esta subseccion se ilustra mejor con un diagrama de secuencia.
- Puede construirse directamente a partir del flujo anterior con flechas entre Meta, FastAPI, AgentRunner, LangGraph, PostgreSQL y WhatsApp outbound.

## 13. Integraciones externas implementadas

### 13.1 Microsoft Graph y OAuth

La integracion con Microsoft permitio construir una conexion autentica con el ecosistema del estudiante. Se implementaron componentes para:

- construir URLs de autorizacion;
- intercambiar `authorization_code`;
- persistir tokens;
- sincronizar calendario;
- proyectar eventos del horario fijo;
- soportar futuras extensiones hacia tareas y correo.

### Imagen recomendada para esta subseccion

- Un diagrama del flujo OAuth.
- Tambien puede usarse una captura del endpoint `/oauth/callback` o de la configuracion de Redirect URI.

### 13.2 Outlook Calendar

Outlook Calendar fue la integracion mas importante del MVP a nivel operativo. Permitio proyectar horarios fijos y, posteriormente, sesiones de estudio o eventos asociados al plan academico.

### Imagen recomendada para esta subseccion

- Pantallazo de Outlook Calendar mostrando bloques sincronizados por Lara.

### 13.3 OpenAI y embeddings

Los modelos de IA se utilizaron de manera controlada para:

- clasificacion de entradas;
- extraccion estructurada;
- apoyo multimodal;
- generacion de respuestas pedagogicas delimitadas;
- generacion de embeddings para el corpus RAG.

El proyecto evito depender del modelo para todo. En las zonas de mayor riesgo operacional, como identidad, fases, consentimiento y validaciones, se privilegio la logica determinista.

### Imagen recomendada para esta subseccion

- Un esquema de uso selectivo de IA: "zonas deterministas" y "zonas asistidas por IA".

## 14. Construccion del sistema RAG de recomendaciones

El desarrollo del RAG fue una pieza diferenciadora del agente academico. En lugar de generar recomendaciones de estudio a partir de conocimiento general y potencialmente inconsistente, se construyo un corpus interno curado de metodos, tecnicas, marcos conceptuales y combinaciones pedagogicas.

El pipeline implementado incluyo:

- lectura de documentos Markdown con metadata;
- validacion de contenido y normalizacion;
- division en chunks estructurados;
- extraccion de relaciones ligeras entre conceptos;
- persistencia en PostgreSQL;
- embeddings para recuperacion semantica;
- retrieval hibrido lexical y vectorial;
- rerank determinista;
- ensamblaje de respuestas grounded con trazabilidad de fuentes.

Esta implementacion fue especialmente valiosa por tres razones:

1. elevo la calidad pedagogica de las respuestas;
2. mejoro la auditabilidad del sistema;
3. desacoplo el conocimiento academico del comportamiento conversacional del agente.

El proyecto decidio correctamente no implementar un GraphRAG pesado, ya que el corpus era pequeno, curado y estructurado. Se adopto en su lugar un RAG hibrido con relaciones explicitas ligeras, mas coherente con el alcance del MVP.

### Imagen recomendada para esta seccion

- Diagrama del pipeline de ingestion y retrieval del RAG.
- Si se requiere una figura mas simple, usar "corpus -> embeddings -> retrieval -> rerank -> respuesta".

## 15. Persistencia y trazabilidad

La persistencia se desarrollo en dos niveles:

- persistencia de dominio en PostgreSQL para estudiantes, horarios, actividades, perfiles, prioridades, planes y metadatos operativos;
- persistencia de checkpoints para LangGraph, con el fin de recuperar el estado conversacional por `thread_id`.

Esta doble persistencia fue indispensable para un sistema que debia:

- recordar en que punto del flujo se encontraba un estudiante;
- conservar datos durables del dominio academico;
- tolerar pausas entre mensajes;
- soportar reanudacion del contexto sin perder coherencia.

Tambien se desarrollaron migraciones SQL y diagnosticos para verificar integridad de tablas, relaciones y consistencia operativa.

### Imagen recomendada para esta seccion

- Diagrama entidad-relacion simplificado.
- Tambien puede usarse una figura separando "datos de dominio" y "checkpoints del agente".

## 16. Despliegue productivo en Azure y puesta en operacion

La puesta en produccion del agente se realizo sobre una arquitectura desplegada en Azure, con integracion directa con Meta WhatsApp Cloud API. Esta etapa fue fundamental porque permitio pasar del entorno de desarrollo local a una operacion accesible por HTTPS, con persistencia en la nube y configuracion segura por variables de entorno.

### 16.1 Archivos creados para despliegue

Se definieron los siguientes artefactos de despliegue:

- [src/api/app.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/api/app.py) como servidor FastAPI de produccion;
- [src/api/agent_runner.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/api/agent_runner.py) como pipeline de canal a agente;
- [main.py](/home/jfjaramillo12/TESIS/academic_agentAI/main.py) como punto de entrada de `uvicorn`;
- [Dockerfile](/home/jfjaramillo12/TESIS/academic_agentAI/Dockerfile) como definicion de imagen multi-stage;
- [.env.example](/home/jfjaramillo12/TESIS/academic_agentAI/.env.example) como plantilla de configuracion;
- [.dockerignore](/home/jfjaramillo12/TESIS/academic_agentAI/.dockerignore) para excluir secretos, caches y archivos no necesarios de la imagen.

Tambien se modificaron:

- [src/agents/support/agent.py](/home/jfjaramillo12/TESIS/academic_agentAI/src/agents/support/agent.py) para admitir `build_agent(*, checkpointer=None)`;
- [pyproject.toml](/home/jfjaramillo12/TESIS/academic_agentAI/pyproject.toml) para incluir dependencias de FastAPI, Uvicorn y el paquete `api`.

### Imagen recomendada para esta subseccion

- Captura del `Dockerfile` o de la estructura de archivos de despliegue.
- Mejor aun, una tabla "archivo - responsabilidad".

### 16.2 Arquitectura de despliegue

La arquitectura de despliegue quedo organizada de la siguiente manera:

`Meta WhatsApp Cloud API
        │  POST /webhook (HTTPS)
        ▼
Azure Container Apps  <- Docker image <- Azure Container Registry
        │
        ├── PostgreSQL Flexible Server (Azure)
        │     └── pgvector extension
        └── Variables de entorno y secretos
              ├── Azure OpenAI keys
              ├── WhatsApp tokens
              └── Microsoft Graph credentials`

Esta arquitectura permitio:

- exponer el agente mediante HTTPS publico;
- recibir eventos de Meta sin infraestructura adicional de balanceo propia;
- mantener el backend empaquetado en contenedor reproducible;
- separar imagen, runtime y datos;
- administrar credenciales mediante configuracion de entorno.

### Imagen recomendada para esta subseccion

- Esta es una de las figuras mas importantes del capitulo.
- Conviene crear un diagrama formal de despliegue en Azure con iconos de Meta, Container Apps, ACR, PostgreSQL y Azure OpenAI.

### 16.3 Flujo de despliegue

La estrategia de despliegue siguio una secuencia operativa:

1. construccion local de la imagen Docker;
2. carga de la imagen hacia Azure Container Registry;
3. aprovisionamiento de PostgreSQL Flexible Server;
4. habilitacion de `pgvector`;
5. ejecucion de migraciones y carga del corpus RAG;
6. creacion de Azure Container Apps;
7. inyeccion de variables de entorno y secretos;
8. publicacion de URL HTTPS;
9. configuracion de webhook de WhatsApp;
10. configuracion del callback OAuth de Microsoft;
11. verificacion de salud y lectura de logs.

Esta secuencia redujo el riesgo de fallos tempranos en produccion, ya que permitio validar primero imagen, conectividad y base de datos antes de abrir el webhook al trafico real.

### Imagen recomendada para esta subseccion

- Una linea de tiempo o flujo de despliegue.
- Tambien puede usarse un diagrama numerado con las once etapas.

### 16.4 Variables de entorno y credenciales

La configuracion productiva requirio credenciales para:

- Azure OpenAI;
- WhatsApp Cloud API;
- Microsoft Graph;
- base de datos PostgreSQL.

La gestion de estas variables fue especialmente importante porque el sistema dependio de varios proveedores externos. Por ello, se mantuvo una plantilla `.env.example` y una configuracion equivalente en Azure Container Apps.

### Imagen recomendada para esta subseccion

- Una tabla de variables de entorno, origen y finalidad.
- No conviene mostrar secretos reales; solo nombres de variables y su descripcion.

### 16.5 Verificacion operativa

Una vez desplegado el sistema, se definieron mecanismos de verificacion basados en:

- `GET /health` para comprobar disponibilidad;
- logs de Azure Container Apps para diagnosticar ejecucion del agente;
- handshake de `GET /webhook` para verificar integracion con Meta;
- pruebas funcionales con mensajes reales en WhatsApp;
- validacion del callback OAuth de Microsoft.

Esta capa operativa fue esencial para pasar de un sistema funcional en local a una solucion demostrable en entorno real.

### Imagen recomendada para esta subseccion

- Captura de respuesta del endpoint `/health`.
- Captura del panel de Meta confirmando el webhook.
- Captura de logs en Azure si se desea mostrar evidencia de operacion.

## 17. Validacion, pruebas y control de calidad

El proyecto no se limito a implementar funcionalidad. Se construyo una base de pruebas amplia para proteger el comportamiento del sistema. Los tests cubrieron, entre otros aspectos:

- onboarding;
- validacion de perfiles;
- captura de horario;
- preview y correccion de horario;
- persistencia;
- sincronizacion con Outlook;
- personalizacion;
- priorizacion;
- recomendacion de estudio;
- RAG;
- tracking;
- replanificacion;
- guardrails de arquitectura;
- checkpointer de LangGraph;
- flujos del canal WhatsApp.

En una de las verificaciones documentadas del baseline del MVP se ejecuto una suite completa de 408 pruebas exitosas. Este dato evidencio que la evolucion del proyecto no se dejo al comportamiento emergente del modelo, sino que estuvo respaldada por un regimen de validacion sistematico.

### Imagen recomendada para esta seccion

- Una tabla de cobertura funcional por grupo de pruebas.
- Una captura de terminal con el resultado de la suite completa tambien puede servir como evidencia.

## 18. Principales problemas presentados durante el desarrollo

Uno de los apartados mas importantes para la tesis fue el de dificultades reales de ingenieria. El proyecto encontro problemas concretos, no solamente retos teoricos.

### 18.1 Crecimiento excesivo del grafo conversacional

Con la ampliacion del producto, el grafo principal comenzo a concentrar demasiados nodos y demasiadas transiciones condicionales. Esto hizo que tareas simples, como agregar una nueva ruta, exigieran modificar puntos centrales del sistema.

### 18.2 Aparicion de fases ambiguas o heredadas

En el estado del agente aparecieron fases heredadas, alias o nodos no completamente alineados con el grafo real. Este problema era delicado porque el checkpointer persistia la fase en base de datos. Si una fase persistida dejaba de existir o perdia correspondencia semantica, la recuperacion del flujo podia degradarse silenciosamente.

### 18.3 Acoplamiento entre nodos y logica de negocio

Varios nodos del grafo crecieron demasiado y acumularon logica que debia vivir en servicios. Este problema reducia reutilizacion y dificultaba transformar esa logica en herramientas del agente.

### 18.4 Estado demasiado grande y con campos redundantes

`AgentState` se convirtio en un hotspot arquitectonico. Algunos campos representaban vistas duplicadas o estados derivados. Esto aumentaba el riesgo de inconsistencia interna y complicaba la construccion de un contexto limpio para el agente.

### 18.5 Desconexion inicial entre RAG y operacion del agente

Aunque el RAG existia y funcionaba, durante una etapa estaba conectado solo en puntos muy concretos. Era necesario convertirlo en una capacidad de primera clase del sistema para que el agente pudiera consultarlo cuando realmente lo necesitara.

### 18.6 Diferencia entre MVP activo y MVP objetivo

Durante varias etapas coexistieron capacidades ya implementadas a nivel de servicio con rutas que todavia no estaban activas automaticamente en el flujo principal. Esto exigio documentar con precision que estaba realmente operativo y que permanecia en activacion controlada.

### 18.7 Complejidad del manejo de horarios reales

La captura de horarios presento problemas por lenguaje natural ambiguo, omision de datos, formatos inconsistentes, cruces de bloques, necesidad de correcciones iterativas y apoyo multimodal no siempre perfecto.

### 18.8 Riesgo operativo en integraciones externas

Las integraciones con Outlook, OAuth y servicios de mensajeria introdujeron fallos ajenos al dominio de negocio, como errores de autorizacion, problemas de sincronizacion o datos incompletos. El sistema tuvo que diseñarse para no destruir el estado local cuando la integracion externa fallaba.

### 18.9 Necesidad de gobernanza arquitectonica

Otra dificultad fue evitar que, conforme el sistema crecia, los desarrollos nuevos rompieran la frontera de capas. Por esta razon se implementaron reglas arquitectonicas y pruebas de guardrail.

### Imagen recomendada para esta seccion

- Una tabla de problemas, impacto y solucion aplicada.
- Tambien puede usarse un diagrama de riesgos priorizados.

## 19. Refactorizacion orientada al fortalecimiento del agente autonomo

En la etapa final del proyecto se ejecuto una refactorizacion de alto impacto cuyo objetivo fue fortalecer la solucion como agente academico autonomo apoyado en herramientas, sin romper la base operativa ya implementada.

Esta refactorizacion no partio de cero. Se apoyo en lo ya desarrollado y se centro en cinco correcciones estructurales:

1. separar el punto de entrada del grafo del nodo de consentimiento;
2. depurar el conjunto de fases del agente;
3. extraer logica de negocio de nodos hacia servicios;
4. consolidar y particionar el estado;
5. convertir RAG y otros dominios en capacidades reutilizables del agente.

El principio rector fue el siguiente:

- los procesos de onboarding debian seguir siendo estructurados y deterministas;
- la etapa operativa del estudiante debia fortalecerse hacia un agente con mayor autonomia para decidir herramientas y orden de accion.

Desde la perspectiva de tesis, esta refactorizacion puede presentarse como la maduracion natural del sistema: primero se construyo una base robusta, luego se abstrajeron servicios, y finalmente se fortalecio una arquitectura de agente con contexto, herramientas y capacidad de composicion.

### Imagen recomendada para esta seccion

- Una figura "antes y despues" de la refactorizacion.
- Muy util un diagrama comparando el grafo amplio inicial con la arquitectura mas modular de servicios y herramientas.

## 20. Logros tecnicos alcanzados

El desarrollo permitio alcanzar varios resultados relevantes:

- se construyo un flujo completo de onboarding con persistencia y validaciones;
- se logro capturar y estructurar horarios complejos;
- se implemento personalizacion de tecnicas de estudio;
- se desarrollo infraestructura de priorizacion, planificacion, tracking y replanificacion;
- se integro el sistema con Outlook y OAuth Microsoft;
- se construyo un RAG especializado y auditado;
- se estabilizo una arquitectura por capas con composition root;
- se establecio una estrategia de pruebas extensa;
- se logro desplegar el agente en Azure con integracion real a WhatsApp.

### Imagen recomendada para esta seccion

- Una tabla de logros tecnicos.
- Otra opcion es una figura tipo checklist de capacidades alcanzadas.

## 21. Lecciones de ingenieria derivadas del proyecto

El proyecto dejo varias lecciones relevantes para una tesis de ingenieria de software aplicada a IA:

### 21.1 No toda capacidad debe resolverse con IA generativa

El sistema funciono mejor cuando la IA se uso en tareas donde realmente aportaba valor, como interpretacion, apoyo multimodal, explicacion pedagogica o retrieval semantico, y no en procesos que requerian exactitud operativa estricta.

### 21.2 Un agente util requiere estado durable y no solo memoria de chat

La utilidad real del sistema dependio de recordar perfil, horarios, prioridades y planes. Sin persistencia de dominio y checkpoints conversacionales, el agente no habria podido operar de forma continua.

### 21.3 La arquitectura importa mas a medida que crecen los dominios

La necesidad de separar `agents`, `services`, `repositories` e `integrations` se volvio evidente cuando el sistema paso de un flujo simple a un conjunto de capacidades interdependientes.

### 21.4 La refactorizacion progresiva fue mas efectiva que una reescritura

La experiencia del proyecto demostro que era mejor encapsular, extraer y reorganizar que rehacer todo. La arquitectura se fortalecio sin perder el avance funcional acumulado.

### 21.5 En sistemas academicos, la confiabilidad operativa es tan importante como la inteligencia

Planificar mal una sesion, perder un horario o sincronizar incorrectamente un calendario afecta directamente la utilidad del sistema. Por ello, las reglas deterministas y las pruebas fueron tan importantes como el componente de IA.

### Imagen recomendada para esta seccion

- Una tabla de lecciones aprendidas.
- Puede incluir tres columnas: hallazgo, evidencia en el proyecto y implicacion para futuras fases.

## 22. Limitaciones y aspectos pendientes

Aun con el grado de avance alcanzado, el sistema mantuvo limitaciones propias de un MVP:

- no todas las capacidades desarrolladas estaban activadas automaticamente en todas las fases;
- ciertas rutas seguian bajo activacion controlada o flags;
- la consolidacion total del agente autonomo requirio una fase final de cierre tecnico;
- algunas integraciones dependieron del comportamiento de servicios externos;
- la robustez frente a toda la variabilidad del lenguaje natural siguio siendo un reto incremental.

No obstante, estas limitaciones no invalidaron el desarrollo. Por el contrario, mostraron un proceso realista de construccion de software complejo, donde la madurez se alcanzo mediante iteracion, verificacion y refactorizacion.

### Imagen recomendada para esta seccion

- Una tabla de limitaciones actuales y trabajo futuro.

## 23. Forma recomendada de usar este insumo en la tesis

Este documento puede convertirse en varios apartados del trabajo de grado:

1. planteamiento tecnico del sistema;
2. metodologia de desarrollo e implementacion;
3. arquitectura de software;
4. diseño conversacional y flujo operacional;
5. integraciones externas;
6. implementacion de WhatsApp y despliegue en Azure;
7. desarrollo del modulo RAG;
8. pruebas y validacion;
9. problemas encontrados y soluciones;
10. resultados, limitaciones y trabajo futuro.

Si se desea una estructura aun mas formal para la tesis, este informe puede dividirse en:

- analisis del problema;
- diseño de la solucion;
- implementacion;
- validacion funcional;
- discusion de resultados.

### Imagen recomendada para esta seccion

- No es indispensable una imagen.
- Si se desea, puede ponerse una tabla de correspondencia entre secciones del informe y capitulos de la tesis.

## 24. Cierre

En sintesis, el desarrollo del agente de IA academico Lara no consistio en ensamblar un sistema de respuesta generativa, sino en construir progresivamente un agente conversacional con memoria operativa, persistencia, integraciones externas, reglas de negocio, personalizacion pedagogica y capacidad de fortalecerse hacia una operacion mas autonoma. El resultado fue una plataforma base solida para apoyar la gestion academica del estudiante, y al mismo tiempo un caso de estudio valioso sobre como integrar IA generativa dentro de una arquitectura de software controlada, verificable y orientada a dominio.

### Imagen recomendada para esta seccion

- Una figura final de arquitectura integral o una captura del sistema en funcionamiento.

## 25. Documentos base utilizados para construir este informe

La redaccion de este insumo se apoyo principalmente en la documentacion tecnica existente del repositorio:

- `docs/arquitectura_big_picture.md`
- `docs/mvp_academic_agent_lara.md`
- `docs/plan_refactorizacion_de_chatbot_a_agente_autonomo.md`
- `docs/2026-04-03/informe_final_arquitectura_cerrada.md`
- `docs/2026-04-18/plan_fases_implementacion_mvp_lara.md`
- `docs/2026-04-18/estado_baseline_mvp_lara.md`
- `docs/2026-04-17/informe_implementacion_rag_fases_a_h.md`
- `docs/2026-04-17/flujo_conversacional_mvp_agente_academico.md`
- `docs/2026-04-05/06_debilidades_y_riesgos.md`
- `docs/2026-04-06/agentstate_refactor_report.md`
- `docs/2026-04-15/informe_ruta_despliegue_whatsapp_azure.md`

Tambien se verifico consistencia con componentes reales del codigo fuente, en particular:

- `src/agents/support/agent.py`
- `src/agents/support/state.py`
- `src/api/app.py`
- `src/api/agent_runner.py`
- `src/bootstrap/container.py`
- `main.py`
- `Dockerfile`
