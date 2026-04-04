# Informe Final De Arquitectura Cerrada

Fecha: 2026-04-03

Documento rector original: `docs/plan_maestro_refactorizacion_arquitectura.md`

Documentos de referencia:

- `docs/informe_arquitectura_actual_agente.md`
- `docs/analisis_recomendaciones_arquitectura_final.md`
- `docs/architecture_rules.md`

## 1. Veredicto ejecutivo

La arquitectura del proyecto puede considerarse **cerrada y lista para seguir evolucionando**.

El sistema quedó como un:

- **monolito modular orientado por grafo**;
- con **arquitectura por capas**;
- con **composition root explícito**;
- y con una **frontera conversacional clara** en `agents/support/`.

En términos prácticos, esto significa:

- el grafo LangGraph sigue siendo el orquestador del agente;
- `services/` es el origen real de la lógica de negocio;
- `repositories/` es el origen real de la persistencia;
- `integrations/` es el origen real de los adaptadores externos;
- `schemas/` concentra contratos estables compartidos;
- `bootstrap/container.py` concentra el wiring del runtime.

Estado final:

- la arquitectura **ya no depende** de una zona gris activa como la antigua `tools/`;
- `state.py` quedó reducido a contrato mínimo del grafo;
- los wrappers legacy internos más grandes fueron retirados;
- el árbol actual favorece que el camino natural para desarrollar algo nuevo sea también el camino correcto.

Residuo transicional aceptado:

- solo queda `src/agents/support/tools/db.py` como shim legacy mínimo hacia `agents.support.dependencies`.

## 2. Qué arquitectura usa hoy el agente

La arquitectura real del proyecto no es microservicios, ni MVC clásico, ni hexagonal pura. Es una combinación pragmática de estos patrones:

### 2.1 Monolito modular orientado por grafo

- todo el sistema sigue desplegándose como una sola aplicación;
- LangGraph define el ciclo conversacional y la máquina de estados;
- el entrypoint operativo es `src/agents/support/agent.py`.

### 2.2 Arquitectura por capas

La dependencia correcta es:

`agents -> services -> repositories/integrations -> schemas/utils`

Eso permite que la conversación dependa de negocio, pero que negocio no dependa de conversación.

### 2.3 Composition root explícito

El wiring central vive en:

- `src/bootstrap/container.py`

Y la frontera semánticamente correcta para el runtime del agente vive en:

- `src/agents/support/dependencies.py`

## 3. Cómo funciona la arquitectura

## 3.1 Flujo general del runtime

1. Una entrada del usuario llega al grafo en `src/agents/support/agent.py`.
2. El grafo lee `AgentState` y la `phase` actual desde `src/agents/support/state.py`.
3. Según la fase y el contenido del estado, el router selecciona el nodo LangGraph correspondiente.
4. El nodo ejecuta una acción puntual o delega a un flujo conversacional especializado bajo `src/agents/support/flows/`.
5. El flujo usa servicios reales por medio de `src/agents/support/dependencies.py`.
6. Los servicios en `src/services/` ejecutan reglas de negocio y coordinan repositorios o integraciones.
7. `repositories/` persiste estado durable y `integrations/` habla con proveedores externos.
8. El nodo o flujo retorna actualizaciones del `AgentState`, mensajes a enviar y la siguiente fase.
9. El grafo vuelve a rutear hasta llegar a espera de entrada o a fin de flujo.

## 3.2 Rol de cada capa

- `src/agents/support/`
  Orquestación conversacional, grafo, nodos, prompts, flujos y ensamblaje del estado.
- `src/services/`
  Casos de uso y lógica de negocio reutilizable.
- `src/repositories/`
  Persistencia durable o in-memory.
- `src/integrations/`
  Clientes y adaptadores externos.
- `src/schemas/`
  DTOs, contratos y modelos compartidos.
- `src/bootstrap/`
  Wiring explícito del runtime.
- `src/utils/`
  Helpers genéricos sin conocimiento de dominio.

## 3.3 Organización final por dominios

La parte conversacional quedó organizada alrededor de:

- onboarding;
- scheduling;
- extracurricular;
- personalization;
- priorities;
- planning;
- replanning.

La parte de negocio quedó organizada alrededor de:

- `services/onboarding`
- `services/personalization`
- `services/priorities`
- `services/planning`
- `services/reminders`
- `services/scheduling`
- `services/sync`

Las integraciones reales quedaron en:

- `integrations/ai`
- `integrations/langgraph`
- `integrations/microsoft_graph`
- `integrations/whatsapp` como placeholder estructural futuro

## 3.4 Estado conversacional

`src/agents/support/state.py` ya no funciona como fachada de medio sistema.

Su contrato público quedó reducido a:

- `AgentState`
- `Phase`
- `make_initial_state`

Los tipos reutilizables ya viven en `schemas/*`, y la lógica utilitaria de dominio quedó fuera de `state.py`.

## 3.5 Qué pasó con `tools/`

`tools/` dejó de ser una zona de trabajo real.

Hoy:

- no contiene helpers de negocio activos;
- no contiene adaptadores importantes;
- no contiene renderers ni lógica nueva;
- solo conserva el shim mínimo `tools/db.py`.

Eso es importante porque elimina el principal punto histórico de ambigüedad arquitectónica.

## 4. Pros de esta arquitectura

## 4.1 Claridad de responsabilidades

Cada capa tiene una responsabilidad dominante y visible. Eso reduce el costo cognitivo al modificar el sistema.

## 4.2 Evolución más segura

Mover lógica a `services/`, persistencia a `repositories/` e integraciones a `integrations/` permite cambiar una capa sin contaminar las demás.

## 4.3 Mejor testabilidad

La arquitectura favorece pruebas por nivel:

- guardrails arquitectónicos;
- tests de flujos conversacionales;
- tests de servicios;
- tests de repositorios;
- smoke del agente y del container.

## 4.4 Entry point estable

El sistema sigue teniendo un centro operativo claro:

- `src/agents/support/agent.py` como orquestador;
- `src/bootstrap/container.py` como composition root.

Eso facilita debugging y onboarding técnico.

## 4.5 Integraciones externas aisladas

OAuth Microsoft, clientes Graph, AI y checkpointer ya no están mezclados con nodos o servicios conversacionales.

## 4.6 Preparación para nuevas capacidades

La estructura ya deja preparado el crecimiento hacia:

- sync adicional;
- RAG;
- nuevos canales como WhatsApp;
- evolución de recomendación de métodos.

Sin necesidad de rehacer la base arquitectónica.

## 5. Riesgos residuales controlados

La arquitectura quedó bien, pero todavía hay decisiones que deben mantenerse con disciplina:

- `tools/db.py` sigue existiendo como shim legado mínimo;
- no existe una carpeta global `prompts/`, y eso debe manejarse por política, no por improvisación;
- `study_methods/` todavía no debe crearse hasta que exista una necesidad real del producto.

Estos puntos ya no son un problema estructural. Son decisiones de gobernanza técnica.

## 6. Recomendaciones para el futuro

## 6.1 Mantener la regla de dependencias

No permitir nuevos atajos como:

- `agents` importando `repositories` o `integrations` directamente;
- lógica de negocio nueva dentro de nodos;
- DTOs compartidos nuevos dentro de `state.py`.

## 6.2 Mantener prompts co-localizados por defecto

Política recomendada:

- prompt local junto al nodo o flujo si es de uso local;
- carpeta compartida solo si un prompt se reutiliza en varios dominios.

No conviene crear una carpeta global de prompts por estética.

## 6.3 No crear `study_methods/` antes de tiempo

Solo debería aparecer si la recomendación de métodos evoluciona a un dominio propio con:

- reglas complejas;
- contenido reusable;
- retrieval o RAG;
- variantes por programa, perfil o contexto.

Mientras eso no exista, crear esa carpeta sería arquitectura anticipada.

## 6.4 Mantener `tools/` congelado

La regla futura debe ser simple:

- nada nuevo se desarrolla en `tools/`;
- si aparece una necesidad real, debe vivir en `agents/support/`, `services/`, `repositories/` o `integrations/` según su responsabilidad.

## 6.5 Reforzar pruebas end-to-end

La arquitectura ya tiene buena cobertura estructural y por flujos, pero el siguiente salto de madurez debe ser:

- pruebas end-to-end del grafo completo;
- pruebas de integración reales con Outlook/To Do en entorno controlado;
- pruebas de regresión de replanificación con escenarios más amplios.

## 6.6 Tratar `dependencies.py` como la frontera oficial del runtime del agente

Si un nodo o flujo necesita un servicio compartido, debe llegar a él por:

- `src/agents/support/dependencies.py`

No por `bootstrap.container` directo y no por nuevos service locators.

## 7. Veredicto final

Sí, la arquitectura ya quedó en un estado bueno, coherente y suficientemente limpio para continuar el desarrollo del proyecto.

La arquitectura final del agente puede describirse como:

- **monolito modular orientado por grafo**
- con **arquitectura por capas**
- y **composition root explícito**

Su principal fortaleza es que separa correctamente:

- conversación;
- negocio;
- persistencia;
- integraciones;
- contratos compartidos.

La recomendación práctica a partir de ahora no es volver a refactorizar la base, sino **desarrollar nuevas capacidades respetando las reglas ya cerradas**.

## 8. Estado de validación

Validación reciente usada como referencia de estabilidad:

- suite amplia de arquitectura y flujos: `160` pruebas pasando;
- smoke adicional del agente y flujos principales: `32` pruebas pasando.

Conclusión operativa:

- el flujo principal del agente quedó funcionando normalmente bajo la arquitectura final actual.
