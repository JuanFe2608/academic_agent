# Metodologia De Auditoria Tecnica Integral

Fecha: 2026-04-05

Estado: fase inicial de auditoria

## 1. Objetivo de la auditoria

Definir una metodologia de auditoria tecnica integral para entender el estado real del proyecto a partir del codigo, la configuracion, las migraciones, las pruebas y la documentacion historica ya existente.

La auditoria busca responder, con evidencia verificable:

- como esta organizado hoy el proyecto;
- que arquitectura real esta implementada;
- como funciona el agente en la practica;
- si la distribucion actual de modulos favorece o perjudica el crecimiento;
- que tan coherentes son la base de datos, las integraciones y la documentacion con el negocio del agente academico.

## 2. Alcance

La auditoria cubrira:

- estructura del repositorio y mapa de modulos;
- entrypoints, runtime y configuracion principal;
- arquitectura real observada en `src/`;
- grafo LangGraph, `AgentState`, nodos, flujos y servicios;
- persistencia: repositorios, migraciones SQL, tablas, relaciones y coherencia con el negocio;
- integraciones externas actuales o previstas: Azure/OpenAI, Microsoft Graph, correo institucional, WhatsApp y posible integracion de Telegram;
- pruebas automatizadas, guardrails y señales de enforcement arquitectonico;
- consistencia entre documentacion historica y codigo actual.

La auditoria se basara en evidencia de:

- `README.md`, `pyproject.toml`, `langgraph.json`;
- `src/`;
- `migrations/`;
- `tests/`;
- `docs/2026-03-25/`, `docs/2026-03-30/`, `docs/2026-04-01/`, `docs/2026-04-03/`.

## 3. Criterios de evaluacion

El analisis usara los siguientes criterios:

1. Coherencia arquitectonica.
   Se verificara si la separacion declarada entre `agents/`, `services/`, `repositories/`, `integrations/`, `schemas/`, `bootstrap/` y `utils/` se cumple realmente en imports, responsabilidades y flujo de dependencias.
2. Claridad de responsabilidades.
   Se evaluara si cada modulo tiene una responsabilidad dominante o si mezcla orquestacion, reglas de negocio, persistencia, integraciones y formato conversacional.
3. Cohesion y acoplamiento.
   Se revisara si cada dominio esta bien encapsulado y si existen dependencias cruzadas, duplicacion de logica, hotspots o acoplamiento accidental.
4. Trazabilidad del flujo del agente.
   Se analizara si el funcionamiento del agente puede explicarse de forma clara desde el grafo, el estado y los servicios sin depender de comportamiento oculto.
5. Coherencia de persistencia.
   Se auditara si las migraciones, entidades, campos, repositorios y contratos reflejan correctamente el negocio del agente academico.
6. Capacidad de crecimiento.
   Se evaluara si la distribucion actual soporta onboarding, horarios, planificacion, recordatorios, replanificacion y nuevos canales sin degradar mantenibilidad.
7. Calidad de enforcement.
   Se revisara si existen pruebas, guardrails o convenciones activas que sostengan la arquitectura y eviten regresiones.

## 4. Orden exacto de analisis

La auditoria se ejecutara en este orden:

1. Baseline documental y de configuracion.
   Lectura de `README.md`, `pyproject.toml`, `langgraph.json` y documentacion historica relevante para entender la arquitectura objetivo, el contexto del refactor y las reglas declaradas.
2. Mapa real del repositorio.
   Inventario de carpetas, modulos, dominios, entrypoints, pruebas y migraciones para identificar la estructura efectiva y los limites entre capas.
3. Arquitectura actual observada en codigo.
   Revision del composition root, el agente principal, el estado, los servicios, repositorios, integraciones y contratos compartidos para determinar el estilo arquitectonico real del proyecto.
4. Flujo funcional del agente.
   Trazado del recorrido desde onboarding hasta scheduling, personalization, priorities, study plan, reminders y replanificacion, explicando que nodo llama a que servicio y que se persiste en cada fase.
5. Analisis modular y de distribucion.
   Evaluacion de por que los archivos estan donde estan, que modulos tienen buena separacion y cuales siguen concentrando demasiada responsabilidad.
6. Auditoria de base de datos y persistencia.
   Relevamiento de migraciones, tablas, entidades, relaciones, claves, campos operativos y alineacion con el negocio del producto.
7. Auditoria de integraciones y extensibilidad.
   Revision de adaptadores externos y evaluacion especifica de como integrar Telegram manteniendo la arquitectura limpia, preferiblemente como adaptador de canal y no como logica incrustada en `agents/`.
8. Consolidacion de hallazgos.
   Separacion explicita entre hechos observados, problemas detectados, riesgos y recomendaciones.
9. Roadmap.
   Definicion de una ruta de mejora solo si la evidencia muestra que aun hay deuda arquitectonica relevante despues del ultimo refactor.

## 5. Fases y artefactos de salida

La auditoria generara los siguientes entregables dentro de `docs/2026-04-05/`:

- `00_metodologia_auditoria.md`
  Define objetivo, alcance, criterios, orden de trabajo y limites de la auditoria.
- `01_mapa_proyecto.md`
  Inventario estructural del repositorio, dominios, entrypoints y modulos principales.
- `02_arquitectura_actual.md`
  Identificacion de la arquitectura real y de las reglas de dependencia efectivamente observadas.
- `03_flujo_agente_actual.md`
  Explicacion del funcionamiento del agente y del recorrido entre nodos, estado, servicios e integraciones.
- `04_analisis_modular.md`
  Evaluacion de modularidad, cohesion, acoplamiento y distribucion de responsabilidades.
- `05_auditoria_base_datos.md`
  Auditoria de migraciones, entidades, campos, relaciones y coherencia con el negocio.
- `06_debilidades_y_riesgos.md`
  Sintesis de problemas, debilidades y riesgos tecnicos priorizados.
- `07_recomendaciones_y_refactor_roadmap.md`
  Recomendaciones y hoja de ruta de mejora, solo si la evidencia lo justifica.
- `08_informe_final_consolidado.md`
  Informe ejecutivo consolidado con conclusiones finales de la auditoria.

## 6. Criterios para detectar problemas

Se considerara hallazgo relevante cuando exista evidencia de alguno de estos patrones:

- desviacion entre la arquitectura documentada y la arquitectura real;
- imports entre capas que rompen la direccion de dependencias esperada;
- nodos LangGraph con demasiada logica de negocio o persistencia incrustada;
- servicios que dependen de detalles conversacionales o de `agents/`;
- repositorios, migraciones o tablas sin correspondencia clara con el negocio;
- duplicacion de logica entre nodos, servicios, helpers o modulos historicos;
- modulos hotspot demasiado grandes o con responsabilidades heterogeneas;
- integraciones externas acopladas a flujos conversacionales en vez de estar encapsuladas;
- carpetas reservadas o placeholders sin contrato de extension claro;
- documentacion desactualizada frente al comportamiento real del codigo;
- gaps de pruebas o guardrails en zonas criticas del sistema;
- crecimiento funcional que obligue a tocar demasiadas capas para cambios pequenos.

Cada hallazgo importante debera presentarse luego en cuatro bloques:

- hechos observados;
- problemas detectados;
- riesgos;
- recomendaciones.

## 7. Criterio de organizacion de `docs`

Antes de iniciar la auditoria se reorganizo `docs/` en carpetas por fecha con formato `YYYY-MM-DD`.

Regla aplicada:

- si el documento declara una fecha explicita, esa fecha gobierna su ubicacion;
- si no la declara, se usa como respaldo la fecha de alta en Git del archivo;
- la nueva auditoria vive en `docs/2026-04-05/`.

Este criterio permite separar antecedentes por corte temporal y facilita distinguir documentos de diagnostico, planes y reportes historicos.

## 8. Que no se va a hacer aun

En esta etapa no se hara lo siguiente:

- no se modificara codigo de aplicacion;
- no se refactorizaran modulos;
- no se borraran archivos;
- no se cambiaran migraciones ni esquema de base de datos;
- no se implementaran integraciones nuevas, incluyendo Telegram;
- no se ejecutaran cambios funcionales en el agente;
- no se asumira que la documentacion historica es verdad sin contrastarla con el codigo;
- no se propondran refactors como obligatorios hasta terminar la evidencia tecnica completa.

## 9. Resultado esperado de esta primera fase

Al cerrar esta fase inicial debe quedar:

- `docs/` organizado por fecha;
- definida la metodologia exacta de auditoria;
- establecido el orden de analisis para las siguientes entregas;
- delimitado claramente que esta auditoria es de analisis y documentacion, no de intervencion sobre codigo.
