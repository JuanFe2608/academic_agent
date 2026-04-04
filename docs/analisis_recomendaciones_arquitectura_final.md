# Análisis De Recomendaciones Técnicas Para Una Arquitectura Limpia Y Final

Fecha: 2026-04-03

Documento base: `docs/informe_arquitectura_actual_agente.md`

## 1. Objetivo del análisis

Este documento evalúa las recomendaciones técnicas propuestas al final de `docs/informe_arquitectura_actual_agente.md` y determina:

- cuáles deben ejecutarse para considerar la arquitectura "final";
- cuáles deben posponerse;
- cuáles no conviene perseguir como objetivo estructural por ahora;
- y en qué orden deben abordarse para no romper el runtime del agente.

## 2. Veredicto ejecutivo

La arquitectura actual ya es **operativamente correcta** y está **bien alineada** con el plan maestro. Sin embargo, si el objetivo es pasar de una "arquitectura operativa limpia" a una **arquitectura final, estable y sin deuda de transición relevante**, no todas las recomendaciones tienen el mismo peso.

Veredicto por recomendación:

1. **Reducir wrappers legacy**
   Estado: obligatorio para cierre final.
   Prioridad: alta.

2. **Decidir si consolidar `prompts/`**
   Estado: decisión de diseño, no bloqueo arquitectónico.
   Prioridad: baja.

3. **Reducir re-exports de `AgentState`**
   Estado: recomendable, pero después de migrar consumidores.
   Prioridad: media.

4. **Crear `services/study_methods/`**
   Estado: no conviene hacerlo todavía.
   Prioridad: baja o nula por ahora.

5. **Limpiar artefactos residuales del árbol antiguo**
   Estado: obligatorio, pero debe hacerse de forma selectiva.
   Prioridad: alta.

Además, hay una recomendación implícita que el informe previo no dejaba lo suficientemente explícita:

6. **Cerrar el service locator transicional (`agents/support/tools/db.py`)**
   Estado: obligatorio si se quiere una arquitectura final realmente limpia.
   Prioridad: muy alta.

## 3. Diagnóstico puntual sobre el estado actual

## 3.1 Lo que ya está resuelto

Ya está correctamente resuelto:

- `services/`, `repositories/`, `integrations/`, `schemas/`, `bootstrap/` y `rag/` existen como capas top-level;
- `agents/` concentra grafo, nodos, flujos y estado;
- `bootstrap/container.py` ya actúa como composition root explícito;
- existen guardrails automáticos de arquitectura;
- el código productivo ya no tiene imports directos impropios hacia `repositories/` o `integrations/`, salvo wrappers permitidos.

Esto significa que la arquitectura **ya es válida**. Lo pendiente es cerrar la deuda de transición.

## 3.2 Dónde sigue viva la compatibilidad legacy

La compatibilidad legacy todavía tiene peso real.

Observaciones del repo:

- `agents.support.tools.db` sigue siendo consumido por varios nodos/flows productivos y por varios tests;
- `agents.support.state` sigue siendo el punto de entrada dominante para `AgentState` y varios re-exports, sobre todo en pruebas;
- todavía existen muchos wrappers físicos en:
  - `src/agents/support/onboarding/`
  - `src/agents/support/personalization/`
  - `src/agents/support/planning/`
  - `src/agents/support/priorities/`
  - `src/agents/support/scheduling/`
  - `src/agents/support/tools/`
- los prompts siguen distribuidos localmente por nodo/flujo y no en una carpeta `prompts/` centralizada.

Conclusión:

- el principal trabajo restante no es "rediseñar" la arquitectura;
- es **apagar la capa de compatibilidad sin romper el grafo ni las pruebas**.

## 4. Análisis de cada recomendación

## 4.1 Reducir wrappers legacy que ya no tengan consumidores

### Evaluación

Esta recomendación sí debe ejecutarse.

Es la recomendación más importante junto con el cierre de `tools/db.py`, porque mientras existan demasiadas fachadas heredadas:

- el mapa real del sistema sigue siendo más difícil de leer;
- las pruebas y el código nuevo pueden seguir consumiendo rutas antiguas;
- la arquitectura final sigue dependiendo de convenciones de transición en vez de contratos definitivos.

### Matiz clave

No todos los archivos dentro de `src/agents/support/*` deben desaparecer.

Hay que distinguir tres categorías:

### A. Wrappers que sí deberían eliminarse en la arquitectura final

Ejemplos típicos:

- `agents/support/onboarding/service.py`
- `agents/support/onboarding/repository.py`
- `agents/support/personalization/service.py`
- `agents/support/personalization/repository.py`
- `agents/support/planning/*service.py`
- `agents/support/planning/*repository.py`
- `agents/support/scheduling/service.py`
- `agents/support/scheduling/repository.py`
- `agents/support/reminders_service.py`
- `agents/support/reminders_repository.py`
- wrappers de `tools/` que solo re-exportan módulos top-level

Estos archivos ya no aportan arquitectura; solo mantienen compatibilidad.

### B. Módulos en `agents/` que sí pueden seguir existiendo

No deben confundirse con "legado" si su responsabilidad sigue siendo conversacional o UI del agente:

- `onboarding/messages.py`
- `onboarding/validators.py`
- `personalization/runtime.py`
- `personalization/formatter.py`
- `scheduling/state_helpers.py`
- `scheduling/render.py`
- `scheduling/contextual_parser.py`
- prompts locales de nodos

Estos no son necesariamente deuda. Muchos de ellos pertenecen legítimamente a `agents/`.

### C. Wrappers que deben tratarse como deuda crítica de cierre

El caso más importante es:

- `agents/support/tools/db.py`

Ese archivo todavía materializa un patrón de service locator heredado. Aunque ya delega a `bootstrap.container`, sigue siendo un acceso indirecto que ensucia la lectura de arquitectura.

### Recomendación final

Sí debe ejecutarse esta recomendación, pero con esta política:

- eliminar wrappers solo si no son parte de la capa conversacional;
- migrar primero tests y consumidores internos;
- borrar solo cuando la ruta vieja ya no tenga valor operativo real.

## 4.2 Decidir si `prompts/` merece consolidarse como carpeta real

### Evaluación

Esta recomendación **no es obligatoria** para tener una arquitectura final limpia.

Hoy los prompts están co-localizados por nodo en múltiples `prompt.py`, más algunos mensajes de onboarding. Eso no es una mala arquitectura por sí misma.

### Análisis

Forzar una carpeta `src/agents/support/prompts/` solo porque aparecía en el árbol objetivo del plan puede empeorar el diseño si:

- rompe la cercanía entre el nodo y su prompt;
- crea un repositorio central de strings sin contexto funcional;
- obliga a navegar más para entender un flujo conversacional.

En sistemas de agentes, la co-localización entre:

- nodo,
- flujo,
- validación,
- y prompt

suele ser más mantenible que una "biblioteca global de prompts" cuando el prompt es local a una interacción.

### Recomendación final

No consolidaría todos los prompts en una carpeta única.

Arquitectura recomendada:

- mantener prompts locales junto al nodo o flujo cuando son de uso local;
- crear una carpeta compartida solo para prompts reutilizados por varios dominios o varios flujos;
- documentar esta convención en vez de imponer una migración física innecesaria.

Conclusión:

- esta recomendación debe reinterpretarse;
- no es “crear `prompts/` sí o sí”;
- es “definir una política estable de ubicación de prompts”.

## 4.3 Evaluar si `AgentState` debe seguir exponiendo tantos re-exports de compatibilidad

### Evaluación

Sí conviene hacerlo, pero no como primer paso.

### Análisis

En producción, el problema ya está bastante contenido:

- el código productivo importa principalmente `AgentState`;
- los guardrails ya impiden que módulos productivos sigan trayendo DTOs movidos desde `agents.support.state`.

El uso residual de re-exports vive sobre todo en:

- tests;
- algunos imports heredados de utilidades antiguas.

Por eso, reducir `state.py` ahora mismo es más un trabajo de estabilización de API que una urgencia estructural.

### Riesgo

Si se hace demasiado pronto:

- se dispara mucho churn en tests;
- se mezclan objetivos de limpieza con objetivos funcionales;
- se puede perder claridad sobre qué cambió realmente en arquitectura y qué cambió solo en imports.

### Recomendación final

Sí debe hacerse, pero en dos pasos:

1. congelar `agents.support.state` como API mínima permitida:
   - `AgentState`
   - `Phase`
   - `make_initial_state`
   - quizá uno o dos alias indispensables de transición
2. migrar tests y consumidores restantes hacia:
   - `schemas/*`
   - `services.scheduling.validation`
   - módulos concretos del dominio correspondiente

Conclusión:

- sí es parte de una arquitectura final limpia;
- pero va **después** del apagado principal de wrappers.

## 4.4 Crear `services/study_methods/`

### Evaluación

No conviene hacerlo todavía.

### Análisis

En este momento, `study_methods` sería una carpeta creada por anticipación, no por necesidad real del diseño.

Eso introduce dos riesgos:

- inflar el árbol arquitectónico con dominios vacíos;
- convertir una hipótesis de producto en deuda estructural.

El plan maestro ya era explícito en esto: `study_methods/` debía aparecer cuando la recomendación de métodos dejara de ser solo scoring y pasara a combinar:

- reglas,
- contenido,
- quizás RAG,
- y contratos propios.

### Criterio correcto para abrir ese dominio

Crear `services/study_methods/` solo si se cumplen al menos dos de estas condiciones:

1. existe lógica propia no trivial de recomendación separable de personalization;
2. hay modelos o contratos específicos de método de estudio;
3. hay integración con RAG o base de conocimiento específica;
4. hay reutilización del mismo dominio desde personalization y planning;
5. aparecen al menos 3 módulos de negocio reales que ya no encajan bien en `services/personalization/`.

### Recomendación final

No abrir `study_methods/` todavía.

Por ahora, mantener esa capacidad dentro de:

- `services/personalization/`
- o eventualmente `services/planning/`

hasta que el producto exija un dominio autónomo.

## 4.5 Limpiar artefactos residuales del árbol antiguo

### Evaluación

Sí, esta recomendación es obligatoria.

Pero debe ejecutarse con una definición precisa de "artefacto residual".

### Análisis

No todo lo que vive en `src/agents/support/` es residuo.

Residuo real es:

- lo que ya no es origen de comportamiento;
- lo que solo re-exporta otra capa;
- lo que solo existe por compatibilidad histórica;
- lo que podría borrarse sin cambiar la arquitectura funcional.

No es residuo real:

- un helper conversacional legítimo;
- un formatter de mensajes del agente;
- validadores de entrada del usuario si son específicos del flujo conversacional;
- prompts locales.

### Recomendación final

La limpieza del árbol antiguo debe ser **semántica**, no cosmética.

Objetivo correcto:

- sacar de `agents/` lo que no pertenezca a conversación;
- dejar en `agents/` lo que sí pertenezca a conversación;
- borrar solo los módulos que ya no expresen una responsabilidad propia.

## 5. Recomendación adicional crítica: cerrar `tools/db.py`

Esta es la recomendación más importante para una arquitectura final realmente limpia.

## 5.1 Por qué es un problema

Aunque `agents/support/tools/db.py` ya no contiene el wiring real, sigue funcionando como:

- fachada de service locator;
- punto informal de acceso a dependencias;
- arrastre semántico del estado anterior de la arquitectura.

Eso genera un mensaje arquitectónico ambiguo:

- el container real vive en `bootstrap/`;
- pero los nodos todavía piden servicios vía `tools/db.py`.

Para una arquitectura final, eso debería resolverse.

## 5.2 Qué hacer

Hay dos caminos válidos:

### Opción recomendada

Eliminar gradualmente `tools/db.py` y hacer que los nodos/flows resuelvan servicios mediante un acceso explícito de runtime más limpio.

Dos variantes posibles:

- un pequeño módulo `agents/support/dependencies.py` con nombre arquitectónicamente correcto y sin semántica de “tools”;
- o factories de nodos/handlers ligadas al container al construir el grafo.

### Opción mínima aceptable

Si no se va a eliminar todavía, entonces debe dejar de llamarse `tools/db.py` en la arquitectura final.

El problema no es solo técnico; también es semántico:

- `tools/` sugiere caja gris;
- `db.py` sugiere acceso directo a infraestructura;
- pero en realidad hoy expone servicios de negocio y dependencias del runtime.

### Recomendación final

Para considerar la arquitectura “final”, este punto debe resolverse.

## 6. Orden recomendado para cerrar la arquitectura

No conviene ejecutar las recomendaciones en el orden en que aparecen listadas en el informe previo.

Orden recomendado real:

### Etapa 1. Apagado de compatibilidad estructural

- migrar tests desde imports legacy hacia rutas reales top-level;
- reducir consumo de wrappers de servicio y repositorio;
- dejar wrappers con cero o casi cero consumidores.

### Etapa 2. Cierre del service locator residual

- reemplazar `agents/support/tools/db.py` por un acceso de dependencias más claro;
- ajustar nodos y flows consumidores;
- mantener el container solo en `bootstrap/`.

### Etapa 3. Contracción del API de `state.py`

- mover tests a imports definitivos;
- reducir re-exports de compatibilidad;
- dejar `state.py` centrado en `AgentState` y ensamblaje.

### Etapa 4. Limpieza semántica del árbol `agents/support/`

- borrar wrappers ya sin consumidores;
- conservar solo módulos conversacionales genuinos;
- revisar si algunos helpers siguen mal ubicados o ya están donde deben estar.

### Etapa 5. Decisiones no críticas

- formalizar política de prompts;
- decidir si se crea o no un espacio compartido de prompts;
- reevaluar `study_methods/` cuando el producto realmente lo necesite.

## 7. Definición de “arquitectura final” para este proyecto

Para este proyecto, una arquitectura final y limpia no significa “sin ningún alias histórico”. Significa:

- `agents/` contiene solo conversación, flujos, prompts, routing y estado;
- `services/` es el origen real de la lógica de negocio;
- `repositories/` es el origen real de la persistencia;
- `integrations/` es el origen real de adaptadores externos;
- no existe una zona gris activa equivalente a la antigua `tools/`;
- `state.py` ya no funciona como fachada de medio sistema;
- los tests dejan de depender masivamente de rutas legacy.

La clave no es solo la carpeta correcta, sino que **el camino natural para desarrollar algo nuevo sea también el camino correcto**.

## 8. Recomendación final consolidada

Si el objetivo es cerrar la arquitectura con criterio de “final”, mi recomendación concreta es:

1. **ejecutar sí o sí** la reducción de wrappers legacy;
2. **cerrar `tools/db.py` como service locator residual**;
3. **contraer `state.py` después de migrar consumidores**;
4. **limpiar artefactos residuales con criterio semántico, no cosmético**;
5. **no forzar `prompts/` ni `study_methods/` todavía**.

En síntesis:

- para una arquitectura final limpia, el trabajo pendiente es principalmente **desactivar compatibilidad transicional**;
- no es rehacer la arquitectura base;
- y tampoco es perseguir carpetas “bonitas” sin valor operacional real.
