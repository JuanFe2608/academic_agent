# Plan Completo Para La Construccion Del RAG De Recomendaciones De Estudio

Fecha: 2026-04-15

Estado: plan rector de implementacion

Documento base actualizado: `docs/2026-04-07/02_informe_pipeline_rag_corpus_estudio.md`

## 1. Decision Principal

La mejor solucion para este proyecto no es empezar con un GraphRAG completo.

La solucion recomendada es:

```text
RAG hibrido estructurado + filtros semanticos + rerank deterministico
+ ensamblaje grounded + relaciones explicitas ligeras
```

En terminos practicos:

- se mantiene PostgreSQL como persistencia principal;
- se usa `pgvector` para busqueda semantica;
- se usa busqueda lexical/FTS para terminos exactos;
- se usa metadata estructurada del corpus para filtrar y rankear;
- se modelan relaciones importantes entre tecnicas, metodos, frameworks y matrices;
- no se introduce una base de grafos ni un pipeline GraphRAG pesado en esta fase.

La razon es que el corpus actual es pequeno, curado y altamente estructurado:

- 8 tecnicas;
- 4 metodos;
- 2 frameworks;
- 1 matriz;
- frontmatter rico;
- secciones Markdown consistentes;
- relaciones ya declaradas en campos como `recommended_combinations` y `contraindicated_combinations`.

GraphRAG es valioso cuando hay muchos documentos no estructurados, relaciones implicitas y preguntas globales sobre comunidades de conocimiento. Este proyecto todavia no tiene ese problema. Introducir GraphRAG completo ahora agregaria costo, complejidad y puntos de falla sin aportar una mejora proporcional para el MVP.

## 2. Objetivo Del RAG En Este Proyecto

El RAG debe mejorar la calidad pedagogica del agente academico sin reemplazar la logica operacional que ya existe.

Objetivos correctos:

- explicar mejor por que se recomienda una tecnica de estudio;
- adaptar una recomendacion segun materia, tipo de actividad, tiempo disponible y senales del estudiante;
- sugerir combinaciones validas de tecnicas;
- detectar contraindicaciones o usos pobres de una tecnica;
- enriquecer sesiones de estudio con instrucciones aplicables;
- responder preguntas del estudiante sobre metodos y tecnicas usando fuentes internas;
- mantener respuestas grounded y auditables.

No objetivos:

- no reemplazar el Radar deterministico de personalizacion;
- no reemplazar el planificador semanal;
- no guardar memoria conversacional dentro del RAG;
- no conectar el RAG directamente desde `agents/support/`;
- no usar RAG como base de datos operacional del estudiante;
- no meter documentos fuente dentro de `src/`.

## 3. Encaje Con La Arquitectura Actual

La regla de dependencia del proyecto es:

```text
agents -> services -> repositories/integrations -> schemas/utils
```

El RAG debe respetar esa regla.

Arquitectura objetivo:

```text
knowledge_base/study_recommendations/
  raw/                                  # fuente canonica del conocimiento
  manifests/                            # inventarios y checksums generados
  processed/
    chunks/                             # chunks reproducibles
    evals/                              # preguntas, goldens y resultados

src/rag/
  ingestion/                            # carga, validacion, normalizacion, chunking
  retrieval/                            # query understanding, filtros, busqueda, rerank
  prompting/                            # ensamblaje grounded y plantillas

src/repositories/rag/
  repository.py                         # PostgreSQL, pgvector, FTS, relaciones

src/services/study_recommendations/
  service.py                            # frontera de negocio que consume RAG
  models.py                             # DTOs internos del caso de uso si aplica

src/schemas/
  rag.py                                # contratos estables compartidos
  study_recommendations.py              # contratos de recomendacion si el servicio los expone

migrations/
  0016_rag_study_recommendations.sql    # schema rag, tablas, indices

tests/
  test_rag_*.py                         # ingestion, normalizacion, chunking, retrieval
```

Regla critica:

```text
agents/support/ -> services/study_recommendations/ -> src/rag + repositories/rag
```

El agente no debe importar `src/repositories/rag` ni clientes de embeddings directamente.

## 4. Problemas Detectados Que Deben Corregirse Antes De Vectorizar

### 4.1 Identificadores no canonicos

El codigo usa `active_recall` como identificador de tecnica.

El corpus tiene el documento:

```text
knowledge_base/study_recommendations/raw/techniques/tecnica_recuperacion_activa_rag.md
```

con:

```yaml
technique_id: recuperacion_activa
```

La matriz ya usa `active_recall`.

Decision:

- el identificador canonico debe ser `active_recall`;
- `recuperacion_activa` queda como alias;
- no se debe cambiar el ID usado por el Radar, el scoring ni el planner, porque ya existe logica operacional apoyada en `active_recall`.

### 4.2 Senales en varios vocabularios

El codigo usa tags como:

- `procrastination`
- `distraction`
- `explanation_gap`
- `passive_review_dependence`
- `rapid_forgetting`
- `note_organization`
- `concept_connections`
- `exact_memory`
- `difficulty_switching_topics`

El corpus usa senales en espanol o semiestructuradas como:

- `procrastina`
- `se_distrae_facil`
- `no_puede_explicar`
- `olvida_rapido`
- `necesita_estructura`
- `relee_mucho`
- `no_se_autoevalua`

Decision:

- crear una taxonomia controlada;
- mantener los tags actuales del codigo para no romper perfiles existentes;
- aceptar aliases desde el corpus;
- normalizar todo al contrato interno antes de indexar y recuperar.

### 4.3 Relaciones importantes estan como texto

El corpus ya contiene relaciones, pero estan en campos o secciones Markdown.

Ejemplos:

- tecnicas recomendadas juntas;
- tecnicas contraindicadas juntas;
- metodos que usan varias tecnicas;
- frameworks que ayudan a decidir entre tecnica y metodo;
- matrices que comparan combinaciones.

Decision:

- extraer relaciones explicitas durante la ingestion;
- persistirlas en `rag.relations`;
- usarlas para rerank y validacion de recomendaciones;
- no introducir una base de grafos todavia.

## 5. Diseno Funcional Del RAG

El RAG debe operar en 5 pasos:

```text
1. entender la necesidad
2. convertir contexto del estudiante a filtros
3. recuperar chunks candidatos
4. rerankear con reglas de dominio
5. ensamblar respuesta grounded
```

### 5.1 Tipos De Consulta

El sistema debe clasificar cada solicitud en una intencion simple:

- `explain_technique`
- `recommend_technique`
- `recommend_method`
- `compare_options`
- `technique_vs_method`
- `combine_techniques`
- `adapt_method`
- `session_guidance`
- `contraindication_check`

Esta clasificacion puede empezar con reglas simples, no con LLM.

Ejemplos:

- Si el estudiante pregunta "que es Feynman", usar `explain_technique`.
- Si pregunta "como estudio para un parcial teorico", usar `recommend_method`.
- Si el planner necesita instrucciones para una sesion con `active_recall`, usar `session_guidance`.
- Si una recomendacion combina dos tecnicas, usar `contraindication_check`.

### 5.2 Contexto De Entrada

El RAG no debe recibir `AgentState` completo.

Debe recibir un DTO especifico:

```text
StudyRecommendationQuery
  query_text
  intent
  student_signals
  top_techniques
  subject_name
  subject_type
  activity_type
  available_minutes
  difficulty
  urgency
  preferred_language
  max_chunks
```

Motivo:

- desacopla el RAG del estado conversacional;
- reduce el riesgo de filtrar informacion sensible;
- permite probar retrieval sin levantar el grafo;
- mantiene la arquitectura limpia.

### 5.3 Salida Del Servicio

La salida debe ser estructurada:

```text
StudyRecommendationResult
  answer
  recommended_techniques
  recommended_methods
  cautions
  combinations
  source_chunks
  relations_used
  confidence
  groundedness_notes
```

No basta devolver texto libre. El agente necesita poder usar la respuesta sin perder trazabilidad.

## 6. Modelo De Datos Recomendado

### 6.1 Schema

Crear un schema dedicado:

```sql
CREATE SCHEMA IF NOT EXISTS rag;
```

### 6.2 Tabla `rag.ingestion_runs`

Objetivo:

- saber que version del corpus se proceso;
- poder repetir y auditar ingestion;
- comparar checksums.

Campos:

- `id`
- `run_id`
- `corpus_name`
- `corpus_version`
- `source_root`
- `status`
- `documents_count`
- `chunks_count`
- `relations_count`
- `metadata_json`
- `started_at`
- `finished_at`

### 6.3 Tabla `rag.documents`

Objetivo:

- registrar cada documento fuente normalizado.

Campos:

- `id`
- `document_id`
- `knowledge_type`
- `document_type`
- `entity_id`
- `name`
- `aliases`
- `status`
- `version`
- `source_path`
- `checksum`
- `metadata_json`
- `ingestion_run_id`
- `created_at`
- `updated_at`

Indices:

- unique `document_id`;
- index por `knowledge_type`;
- index por `entity_id`;
- index por `checksum`.

### 6.4 Tabla `rag.chunks`

Objetivo:

- guardar unidades recuperables.

Campos:

- `id`
- `chunk_id`
- `document_id`
- `knowledge_type`
- `document_type`
- `entity_id`
- `section_title`
- `heading_path`
- `chunk_kind`
- `content`
- `content_tsv`
- `metadata_json`
- `embedding`
- `position_in_document`
- `token_estimate`
- `checksum`
- `ingestion_run_id`
- `created_at`
- `updated_at`

Indices:

- unique `chunk_id`;
- FK a `rag.documents(document_id)`;
- GIN sobre `content_tsv`;
- vector index sobre `embedding`;
- index por `knowledge_type`;
- index por `chunk_kind`;
- index por `entity_id`;
- index por `metadata_json` si se usa JSONB para filtros.

Nota:

- la dimension del vector debe depender del modelo de embeddings configurado;
- no se debe quemar esa dimension en codigo de dominio;
- el modelo debe vivir en settings como `RAG_EMBEDDING_MODEL`.

### 6.5 Tabla `rag.relations`

Objetivo:

- tener una capa "graph-aware" ligera sin introducir GraphRAG completo.

Campos:

- `id`
- `relation_id`
- `source_type`
- `source_id`
- `relation_type`
- `target_type`
- `target_id`
- `weight`
- `evidence_text`
- `source_document_id`
- `source_chunk_id`
- `metadata_json`
- `ingestion_run_id`
- `created_at`

Tipos de relacion iniciales:

- `recommended_with`
- `contraindicated_with`
- `uses_component`
- `excludes`
- `routes_to`
- `compares_with`
- `supports_signal`
- `best_for_activity`
- `not_ideal_for_activity`

Ejemplos:

```text
active_recall -> recommended_with -> repeticion_espaciada
cornell -> recommended_with -> active_recall
mnemotecnia -> contraindicated_with -> comprension_profunda_como_objetivo_unico
metodo_parcial_teorico -> uses_component -> active_recall
marco_decision_tecnica_vs_metodo -> routes_to -> study_method
```

## 7. Pipeline De Ingestion

### 7.1 Fase 0: contrato del corpus

Implementar validacion sobre `knowledge_base/study_recommendations/raw/`.

Validaciones:

- todo archivo debe tener frontmatter YAML;
- todo documento debe tener `knowledge_type`;
- todo documento debe tener identificador estable;
- `technique_id`, `method_id`, `framework_id` o `matrix_id` debe existir segun tipo;
- `name`, `status` y `version` son obligatorios;
- la ruta fisica debe coincidir con el tipo semantico;
- debe existir heading principal;
- debe tener headings `##`;
- debe tener al menos una seccion reusable o de guia operacional.

Salida:

```text
knowledge_base/study_recommendations/manifests/document_inventory.json
```

Criterio de aceptacion:

- el comando de validacion falla si hay un documento mal formado;
- el inventario incluye checksum por archivo;
- el inventario muestra IDs canonicos y aliases.

### 7.2 Fase 1: normalizacion

Crear normalizadores para:

- IDs de tecnica;
- tipos de conocimiento;
- tipos de actividad;
- tipos de materia;
- senales del estudiante;
- niveles de evidencia;
- niveles de confianza;
- combinaciones recomendadas y contraindicadas.

Decision de ID:

```text
recuperacion_activa -> active_recall
```

Alias conservados:

```text
active_recall:
  - recuperacion_activa
  - recuperacion activa
  - practica de recuperacion
```

Salida:

```text
NormalizedRagDocument
NormalizedRagMetadata
NormalizedRagRelation
```

Criterio de aceptacion:

- ningun chunk queda con `recuperacion_activa` como ID canonico;
- las relaciones quedan apuntando a IDs canonicos;
- se preserva el texto fuente para trazabilidad.

### 7.3 Fase 2: chunking estructural

No usar chunking por tamano fijo como estrategia principal.

Regla base:

- chunk por seccion `##`;
- preservar tablas completas;
- fusionar subsecciones `###` cuando separarlas rompa una decision;
- crear chunks especiales para respuestas reusables.

Tipos de chunk:

- `definition`
- `objective`
- `use_case`
- `contraindication`
- `steps`
- `quality_control`
- `adaptation`
- `combination`
- `evidence`
- `agent_guidance`
- `answer_ready`
- `comparison`
- `matrix`

Reglas por documento:

- Tecnicas: chunks pequenos por seccion.
- Metodos: chunks por seccion, pero conservar adaptaciones completas.
- Frameworks: chunks orientados a decision y clasificacion.
- Matrices: no partir tablas; preservar contexto de comparacion.

Salida:

```text
knowledge_base/study_recommendations/processed/chunks/chunks.jsonl
knowledge_base/study_recommendations/manifests/chunk_manifest.json
```

Criterio de aceptacion:

- cada chunk tiene `chunk_id` estable;
- cada chunk tiene metadata propia;
- cada chunk referencia `document_id`;
- cada chunk tiene checksum;
- una muestra manual de chunks conserva sentido pedagogico.

### 7.4 Fase 3: extraccion de relaciones

Extraer relaciones desde:

- frontmatter;
- secciones de combinaciones;
- secciones de contraindicaciones;
- matriz de combinacion;
- frameworks de decision.

Salida:

```text
knowledge_base/study_recommendations/manifests/relation_manifest.json
```

Criterio de aceptacion:

- relaciones normalizadas a IDs canonicos;
- relaciones con fuente (`document_id` y si aplica `chunk_id`);
- no hay relaciones duplicadas sin control;
- una recomendacion combinada puede revisar contraindicaciones antes de responder.

### 7.5 Fase 4: persistencia local y reproducible

Antes de embeddings:

- generar manifests;
- generar chunks JSONL;
- ejecutar tests de ingestion;
- revisar diff de artefactos;
- solo entonces pasar a DB.

Esto evita llenar PostgreSQL con datos mal normalizados.

## 8. Pipeline De Embeddings Y Persistencia

### 8.1 Configuracion

Agregar settings:

```text
RAG_ENABLED
RAG_CORPUS_ROOT
RAG_CORPUS_NAME
RAG_EMBEDDING_PROVIDER
RAG_EMBEDDING_MODEL
RAG_EMBEDDING_DIMENSIONS
RAG_TOP_K_VECTOR
RAG_TOP_K_LEXICAL
RAG_TOP_K_FINAL
RAG_MIN_SCORE
```

Regla:

- el agente debe poder funcionar con `RAG_ENABLED=false`;
- si RAG falla, el flujo operativo no debe caerse;
- el servicio puede devolver una respuesta fallback sin fuentes RAG.

### 8.2 Insercion

Orden:

1. crear `rag.ingestion_runs`;
2. upsert de `rag.documents`;
3. upsert de `rag.chunks` sin embedding;
4. generar embeddings por lote;
5. actualizar `rag.chunks.embedding`;
6. upsert de `rag.relations`;
7. cerrar ingestion run.

### 8.3 Reindexado

Regla:

- si cambia el checksum de un documento, se regeneran sus chunks;
- si cambia el chunk content, se regenera su embedding;
- si no cambia, se conserva embedding;
- nunca borrar todo el corpus en produccion sin run auditado.

## 9. Retrieval

### 9.1 Flujo

```text
StudyRecommendationQuery
  -> query understanding
  -> filtros por metadata
  -> vector search
  -> lexical search
  -> merge candidatos
  -> rerank deterministico
  -> expansion por relaciones
  -> grounded context package
```

### 9.2 Query understanding

Primera version:

- reglas por palabras clave;
- IDs de tecnica detectados por alias;
- IDs de metodo detectados por alias;
- senales del estudiante tomadas del perfil;
- actividad/materia desde el planner o input del usuario.

No usar LLM al inicio salvo que las reglas se vuelvan insuficientes.

### 9.3 Filtros

Filtros iniciales:

- `knowledge_type`;
- `document_type`;
- `entity_id`;
- `chunk_kind`;
- `activity_types`;
- `subject_types`;
- `student_profiles`;
- `signals`;
- `evidence_level`;
- `confidence_level`.

Regla:

- los filtros deben reducir ruido, no dejar la consulta sin resultados;
- si un filtro deja cero resultados, degradar de forma controlada.

### 9.4 Hybrid retrieval

Ejecutar:

- busqueda vectorial para similitud semantica;
- busqueda lexical para nombres exactos y terminos del corpus;
- combinar resultados por `chunk_id`.

La busqueda lexical es importante porque el corpus tiene nombres especificos:

- `Pomodoro`;
- `Feynman`;
- `Cornell`;
- `active_recall`;
- `interleaving`;
- `metodo_parcial_teorico`;
- `matriz_de_combinacion_de_tecnicas_para_metodos_de_estudio`.

### 9.5 Rerank deterministico

Score sugerido:

```text
final_score =
  semantic_score
  + lexical_score
  + metadata_match_score
  + chunk_kind_boost
  + relation_boost
  + evidence_boost
  - contraindication_penalty
```

Boosts:

- `answer_ready`;
- `agent_guidance`;
- coincidencia de `signals`;
- coincidencia de `activity_type`;
- coincidencia de tecnica principal del Radar;
- `confidence_level` alto;
- `evidence_level` alto.

Penalizaciones:

- contraindicacion aplicable;
- tecnica no ideal para la actividad;
- chunks sin metadata suficiente;
- chunks demasiado genericos cuando la consulta es especifica.

### 9.6 Expansion por relaciones

Despues del top inicial:

- si aparece una tecnica, buscar relaciones `recommended_with`;
- si hay combinacion, revisar `contraindicated_with`;
- si la consulta es de metodo, traer `uses_component`;
- si hay comparacion, traer matriz o framework relacionado.

Esto entrega valor tipo GraphRAG sin el costo de GraphRAG completo.

## 10. Ensamblaje Grounded

La capa `src/rag/prompting/` debe construir un paquete de contexto, no una respuesta improvisada.

Entrada:

```text
GroundedContextPackage
  query
  selected_chunks
  relations
  constraints
  citations
```

Reglas:

- separar hechos recuperados de inferencias;
- citar `document_id`, `section_title` y `chunk_id`;
- no recomendar una combinacion si existe contraindicacion aplicable;
- si la evidencia es baja, decirlo en la salida estructurada;
- si no hay fuentes suficientes, responder con fallback honesto.

Formato de respuesta interna:

```text
answer:
  Texto final para el estudiante.

sources:
  - document_id
  - chunk_id
  - section_title

cautions:
  - contraindicaciones o limites

recommendation_payload:
  recommended_techniques
  recommended_methods
  combinations
  next_action
```

## 11. Servicio De Negocio

Crear:

```text
src/services/study_recommendations/
```

Responsabilidad:

- recibir contexto de personalizacion, planning o conversacion;
- construir `StudyRecommendationQuery`;
- llamar retrieval;
- convertir resultado RAG a respuesta de negocio;
- definir fallbacks cuando RAG no este disponible.

Metodos iniciales:

```text
explain_technique(...)
recommend_for_student(...)
recommend_for_session(...)
adapt_method_for_subject(...)
validate_technique_combination(...)
```

Regla:

- `services/study_recommendations` no debe conocer detalles del grafo LangGraph;
- `agents/support` solo consume el servicio.

## 12. Integracion Con El Flujo Actual Del Agente

### 12.1 Personalizacion

El Radar actual sigue siendo la fuente primaria de ranking.

RAG entra para:

- explicar mejor el resultado;
- convertir `top_techniques` en recomendaciones pedagogicas;
- agregar contraindicaciones;
- sugerir combinaciones.

No entra para:

- recalcular scores;
- cambiar directamente el ranking sin regla explicita;
- modificar el perfil persistido sin pasar por servicios existentes.

### 12.2 Planificacion Semanal

El planner actual usa tecnica principal para:

- duracion de sesion;
- spacing;
- interleaving;
- reglas de distribucion.

RAG entra para:

- generar instrucciones de sesion;
- proponer estructura interna de una sesion;
- explicar por que una tecnica encaja con una materia;
- agregar tips de calidad.

No entra para:

- decidir horarios;
- saltarse restricciones duras;
- crear eventos directamente.

### 12.3 Seguimiento Diario

RAG puede enriquecer:

- mensajes de acompanamiento;
- recomendaciones para una sesion atrasada;
- consejos ante baja adherencia;
- cambios de tecnica cuando una estrategia no funciona.

### 12.4 WhatsApp

Para WhatsApp, el RAG debe ser:

- rapido;
- tolerante a fallos;
- trazable;
- con respuestas cortas por defecto;
- sin adjuntar chunks largos al usuario.

Regla:

- WhatsApp no debe enviar todo el contexto recuperado;
- el servicio debe ensamblar una respuesta final breve y accionable;
- fuentes internas pueden guardarse en logs/metadata, no necesariamente mostrarse completas al estudiante.

## 13. Evaluacion

Antes de conectar al agente, crear evals en:

```text
knowledge_base/study_recommendations/processed/evals/
```

### 13.1 Dataset minimo

Crear al menos:

- 10 preguntas de definicion;
- 10 preguntas de recomendacion de tecnica;
- 10 preguntas de recomendacion de metodo;
- 10 preguntas de comparacion;
- 10 preguntas con restricciones de materia/actividad;
- 10 preguntas negativas donde una tecnica no conviene;
- 10 preguntas de combinacion de tecnicas.

### 13.2 Formato sugerido

```json
{
  "eval_id": "recommend_technique_001",
  "query": "Me distraigo mucho y me cuesta empezar, que tecnica me conviene?",
  "intent": "recommend_technique",
  "student_signals": ["distraction", "procrastination"],
  "expected_entities": ["pomodoro"],
  "expected_chunk_kinds": ["answer_ready", "agent_guidance", "use_case"],
  "forbidden_entities": ["mnemotecnia"],
  "notes": "Debe priorizar estructura de inicio y foco."
}
```

### 13.3 Metricas

Retrieval:

- Recall@k;
- Precision@k;
- MRR;
- cobertura de entidades esperadas;
- cobertura de chunk kinds esperados.

Calidad:

- groundedness;
- contradiccion con metadata;
- uso correcto de contraindicaciones;
- claridad de recomendacion;
- utilidad accionable.

### 13.4 Criterios minimos antes de integrar

- Recall@5 alto en definiciones y tecnicas;
- cero recomendaciones que contradigan contraindicaciones explicitas;
- respuestas con al menos una fuente interna cuando RAG esta activo;
- fallback correcto cuando no hay chunks suficientes;
- no romper tests existentes del agente.

## 14. Plan De Implementacion Por Fases

### Fase A: base de ingestion sin DB

Objetivo:

- validar corpus;
- normalizar metadata;
- generar chunks;
- extraer relaciones;
- crear manifests reproducibles.

Archivos probables:

```text
src/schemas/rag.py
src/rag/ingestion/contracts.py
src/rag/ingestion/frontmatter.py
src/rag/ingestion/normalization.py
src/rag/ingestion/chunking.py
src/rag/ingestion/relations.py
src/rag/ingestion/pipeline.py
scripts/build_rag_corpus.py
tests/test_rag_ingestion_contract.py
tests/test_rag_normalization.py
tests/test_rag_chunking.py
tests/test_rag_relations.py
```

Entregables:

- inventario de documentos;
- chunks JSONL;
- manifest de relaciones;
- tests unitarios.

No incluye:

- embeddings;
- DB;
- integracion con agente.

### Fase B: persistencia RAG y pgvector

Objetivo:

- crear schema `rag`;
- insertar documentos, chunks y relaciones;
- preparar embeddings.

Archivos probables:

```text
migrations/0016_rag_study_recommendations.sql
src/repositories/rag/__init__.py
src/repositories/rag/repository.py
tests/test_rag_repository.py
```

Entregables:

- migracion SQL;
- repositorio PostgreSQL;
- upsert idempotente;
- indices FTS y vectoriales;
- pruebas con repositorio in-memory o fake donde aplique.

### Fase C: embeddings

Objetivo:

- generar embeddings por lote;
- guardar embeddings solo para chunks nuevos o modificados;
- permitir reindexado incremental.

Archivos probables:

```text
src/integrations/embeddings/__init__.py
src/integrations/embeddings/openai_client.py
src/rag/ingestion/embedding_pipeline.py
tests/test_rag_embedding_pipeline.py
```

Regla arquitectonica:

- el cliente externo vive en `integrations`;
- `src/rag/ingestion` coordina el pipeline;
- el servicio de negocio no llama embeddings directamente.

### Fase D: retrieval hibrido

Objetivo:

- implementar busqueda vectorial + lexical;
- merge;
- rerank;
- expansion por relaciones.

Archivos probables:

```text
src/rag/retrieval/query.py
src/rag/retrieval/filters.py
src/rag/retrieval/hybrid.py
src/rag/retrieval/rerank.py
src/rag/retrieval/relations.py
src/rag/retrieval/context.py
tests/test_rag_retrieval_filters.py
tests/test_rag_rerank.py
tests/test_rag_relation_expansion.py
```

Entregables:

- retrieval deterministico probado;
- top chunks explicables;
- manejo de cero resultados;
- no depender de LangGraph para probar.

### Fase E: prompting grounded

Objetivo:

- ensamblar contexto recuperado;
- crear respuesta final estructurada;
- aplicar reglas de seguridad pedagogica.

Archivos probables:

```text
src/rag/prompting/context_package.py
src/rag/prompting/grounded_answer.py
src/rag/prompting/templates.py
tests/test_rag_grounded_prompting.py
```

Entregables:

- respuesta con fuentes internas;
- cautions;
- payload estructurado;
- fallback honesto.

### Fase F: servicio de recomendaciones

Objetivo:

- abrir frontera de negocio para el agente.

Archivos probables:

```text
src/services/study_recommendations/__init__.py
src/services/study_recommendations/models.py
src/services/study_recommendations/service.py
tests/test_study_recommendation_service.py
```

Entregables:

- `recommend_for_student`;
- `recommend_for_session`;
- `explain_technique`;
- `validate_technique_combination`;
- fallbacks sin RAG.

### Fase G: integracion controlada con agente

Objetivo:

- usar el servicio RAG solo en puntos de bajo riesgo.

Orden recomendado:

1. enriquecer explicacion final del Radar;
2. enriquecer instrucciones de sesion del plan semanal;
3. responder preguntas directas sobre tecnicas/metodos;
4. usar contraindicaciones para validar combinaciones;
5. despues, evaluar si conviene usar RAG en replanning.

Regla:

- no conectar RAG en todos los nodos a la vez;
- cada punto de integracion debe tener tests de flujo.

### Fase H: evaluacion y hardening

Objetivo:

- medir calidad antes de produccion.

Entregables:

- dataset de evals;
- runner de evals;
- reporte de metricas;
- casos negativos;
- pruebas de latencia;
- pruebas con `RAG_ENABLED=false`.

## 15. Orden Recomendado De Trabajo

Orden concreto:

1. cerrar taxonomia de IDs y senales;
2. implementar contratos Pydantic del RAG;
3. implementar parser de frontmatter;
4. implementar validador de corpus;
5. implementar normalizador;
6. implementar chunker estructural;
7. implementar extractor de relaciones;
8. generar manifests y chunks;
9. crear pruebas unitarias;
10. crear migracion `rag`;
11. implementar repositorio;
12. implementar embeddings;
13. implementar retrieval hibrido;
14. implementar rerank;
15. implementar prompting grounded;
16. crear servicio `study_recommendations`;
17. crear evals;
18. integrar con el agente en un punto pequeno;
19. ampliar integracion solo despues de medir.

## 16. Criterios Para Decidir Si Luego Se Necesita GraphRAG

Evaluar GraphRAG solo si aparecen estas condiciones:

- el corpus crece a cientos o miles de documentos;
- entran PDFs largos y poco estructurados;
- las relaciones importantes ya no estan explicitas;
- se necesitan preguntas globales tipo "que comunidades de estrategias existen";
- se necesita descubrir patrones no escritos en metadata;
- el retrieval hibrido empieza a fallar por falta de estructura relacional.

Mientras el corpus siga siendo pequeno, curado y con metadata rica, el enfoque graph-aware ligero es mas adecuado.

## 17. Riesgos Y Controles

| Riesgo | Impacto | Control |
| --- | --- | --- |
| IDs inconsistentes entre corpus y codigo | recomendaciones incorrectas | taxonomia canonica y aliases |
| RAG reemplaza reglas deterministicas | rompe planner/personalizacion | RAG solo en servicio de recomendacion, no en scoring |
| Chunks demasiado pequenos | perdida de contexto | chunking por seccion, preservar tablas |
| Chunks demasiado grandes | baja precision | chunk kinds y rerank |
| Embeddings obsoletos | retrieval inconsistente | checksums y reindexado incremental |
| Respuestas no grounded | alucinacion | fuentes obligatorias y fallback |
| Latencia alta en WhatsApp | mala experiencia | top_k limitado, cache, respuestas cortas |
| Dependencia fuerte de proveedor de embeddings | bloqueo operacional | cliente en integrations y settings |
| DB operacional contaminada | mantenimiento dificil | schema `rag` separado |
| Integracion prematura en el grafo | regresiones | servicio intermedio y rollout por fases |

## 18. Politica De Commits Y Artefactos

Debe versionarse:

- codigo en `src/rag/`;
- codigo en `src/services/study_recommendations/`;
- codigo en `src/repositories/rag/`;
- migraciones SQL;
- documentos fuente en `knowledge_base/study_recommendations/raw/`;
- manifests si se decide que son parte reproducible del corpus;
- evals curadas;
- tests.

No debe versionarse:

- embeddings exportados como archivos locales grandes;
- dumps de DB;
- secretos;
- cache local;
- salidas temporales de corrida;
- artefactos generados enormes.

Si `processed/chunks/` se vuelve grande, decidir si:

- se versiona solo en MVP para auditoria;
- o se regenera siempre en CI/CD y se excluye del repo.

Para este MVP, se recomienda versionar chunks JSONL mientras sean pequenos, porque ayudan a revisar calidad del pipeline.

## 19. Comandos Objetivo

Los comandos finales deberian parecerse a esto:

```bash
PYTHONPATH=src python scripts/build_rag_corpus.py --validate-only
PYTHONPATH=src python scripts/build_rag_corpus.py --write-artifacts
PYTHONPATH=src python scripts/build_rag_corpus.py --sync-db
PYTHONPATH=src python scripts/build_rag_corpus.py --embed-changed
PYTHONPATH=src python scripts/evaluate_rag.py
```

No es necesario implementar todos desde el primer commit. El primer commit debe enfocarse en:

```bash
PYTHONPATH=src python scripts/build_rag_corpus.py --validate-only
PYTHONPATH=src python scripts/build_rag_corpus.py --write-artifacts
```

## 20. Definicion De Terminado Del Primer Incremento

El primer incremento se considera terminado cuando:

- el corpus completo se valida sin errores;
- `active_recall` queda como ID canonico;
- `recuperacion_activa` queda como alias;
- se generan inventario, chunks y relaciones;
- los chunks son estables entre corridas si no cambia el corpus;
- hay tests unitarios de validacion, normalizacion, chunking y relaciones;
- no se toca el flujo conversacional del agente;
- no se toca el planner;
- no se requiere PostgreSQL ni embeddings todavia.

Este primer incremento reduce riesgo y deja la base lista para pgvector.

## 21. Conclusion

El plan anterior del 7 de abril era correcto en la direccion general: RAG por tipo de conocimiento, filtros semanticos, chunking estructural y persistencia separada.

La mejora de este nuevo plan es que baja esa idea a una arquitectura ejecutable:

- define frontera de servicio;
- define modelo de datos;
- agrega relaciones ligeras tipo graph-aware;
- corrige el problema de IDs;
- protege el Radar y el planner actuales;
- define fases verificables;
- prepara WhatsApp y despliegue sin acoplarlos al RAG;
- deja criterios claros para saber si algun dia conviene GraphRAG.

La recomendacion final es implementar primero la ingestion robusta sin DB. Despues, y solo despues de validar chunks y relaciones, avanzar a pgvector, retrieval hibrido y servicio de recomendaciones.
