# Informe De Implementacion Del RAG De Recomendaciones De Estudio

Fecha: 2026-04-17

Estado: fases A-H implementadas, revisadas y verificadas en backend local.

Documento rector: `docs/2026-04-15/plan_completo_construccion_rag_estudio.md`

## 1. Resumen Ejecutivo

Se implemento el RAG de recomendaciones de estudio siguiendo la decision arquitectonica del plan:

```text
RAG hibrido estructurado + filtros semanticos + rerank deterministico
+ ensamblaje grounded + relaciones explicitas ligeras
```

No se implemento GraphRAG completo. La decision sigue siendo correcta para el MVP porque el corpus es pequeno, curado y estructurado:

- 15 documentos fuente.
- 468 chunks.
- 355 relaciones explicitas.
- metadata rica en frontmatter.
- taxonomia controlada de tecnicas, metodos, senales, actividades y tipos de conocimiento.

La implementacion quedo integrada respetando la frontera principal del proyecto:

```text
agents/support -> services/study_recommendations -> src/rag + repositories/rag + integrations/embeddings
```

El agente no importa directamente `rag`, `repositories.rag` ni `integrations.embeddings`.

## 2. Objetivo Del RAG

El RAG se construyo para mejorar la calidad pedagogica del agente academico sin reemplazar la logica operacional ya existente.

Objetivos cubiertos:

- explicar tecnicas y metodos de estudio con fuentes internas;
- recomendar tecnicas segun senales del estudiante;
- recomendar o adaptar metodos segun materia, actividad y tiempo disponible;
- validar combinaciones de tecnicas;
- detectar contraindicaciones y usos pobres;
- enriquecer una sesion de estudio con instrucciones breves;
- enriquecer el resumen de personalizacion con una explicacion pedagogica;
- mantener respuestas auditables mediante `source_chunks`, `relations_used` y `groundedness_notes`.

Objetivos que se evitaron correctamente:

- no reemplazar el Radar deterministico de personalizacion;
- no reemplazar el planner semanal;
- no convertir el RAG en memoria conversacional;
- no conectar RAG directamente desde nodos del agente hacia repositorios o embeddings;
- no usar documentos fuente dentro de `src/`;
- no introducir base de grafos ni GraphRAG pesado.

## 3. Arquitectura Final

La arquitectura final quedo separada por responsabilidades:

```text
knowledge_base/study_recommendations/
  raw/                       # corpus canonico curado
  manifests/                 # inventarios y checksums generados
  processed/
    chunks/                  # chunks reproducibles
    evals/                   # dataset, README y reportes generados ignorados

src/schemas/rag.py           # contratos estables

src/rag/
  ingestion/                 # parser, validacion, normalizacion, chunking, relaciones
  retrieval/                 # query understanding, filtros, busqueda hibrida, rerank
  prompting/                 # ensamblaje grounded y plantillas
  evaluation/                # evaluacion offline y metricas

src/repositories/rag/        # persistencia PostgreSQL + pgvector + FTS
src/integrations/embeddings/ # clientes OpenAI/Azure OpenAI embeddings
src/services/study_recommendations/
                            # frontera de negocio consumida por el agente

src/agents/support/          # integracion controlada via servicio
```

La regla de dependencia queda asi:

```text
agents -> services -> repositories/integrations -> schemas/utils
```

`src/rag` contiene logica de conocimiento, no logica conversacional del agente. `src/services/study_recommendations` es la frontera que adapta el RAG al caso de uso del agente.

## 4. Pipeline Completo

El pipeline completo quedo dividido en dos rutas: ingestion/indexacion y consulta.

### 4.1 Pipeline De Ingestion E Indexacion

Entrada:

```text
knowledge_base/study_recommendations/raw/**/*.md
```

Pasos:

1. Leer Markdown con frontmatter.
2. Validar metadata minima.
3. Normalizar identificadores y senales.
4. Generar documentos normalizados.
5. Dividir documentos en chunks por seccion.
6. Clasificar cada chunk por `chunk_kind`.
7. Extraer relaciones explicitas desde metadata.
8. Escribir artefactos reproducibles.
9. Sincronizar documentos/chunks/relaciones en PostgreSQL.
10. Generar embeddings solo para chunks nuevos o modificados.

Comandos:

```bash
uv run python scripts/build_rag_corpus.py --validate-only
uv run python scripts/build_rag_corpus.py --write-artifacts
uv run python scripts/build_rag_corpus.py --sync-db
uv run python scripts/build_rag_corpus.py --embed-changed
```

Estado verificado:

```text
documents: 15
chunks: 468
relations: 355
issues: 0
```

### 4.2 Pipeline De Consulta

Entrada:

```text
StudyRecommendationQuery
```

Pasos:

1. Entender la consulta con reglas deterministicas.
2. Detectar intencion: definicion, recomendacion, comparacion, combinacion, guia de sesion, contraindicacion, etc.
3. Detectar tecnicas, metodos y senales del estudiante.
4. Convertir senales a filtros y, cuando aplica, a tecnica primaria.
5. Construir filtros estructurales por tipo de conocimiento, entidad y tipo de chunk.
6. Ejecutar retrieval hibrido:
   - busqueda lexical con PostgreSQL FTS;
   - busqueda vectorial con pgvector;
   - fallback controlado si faltan vectores o filtros estrictos no traen candidatos.
7. Unificar candidatos lexicales y vectoriales.
8. Rerankear con reglas de dominio:
   - similitud semantica;
   - score lexical;
   - coincidencia de metadata;
   - prioridad por chunk kind;
   - relaciones explicitas;
   - evidencia/confianza;
   - penalizaciones por contraindicaciones.
9. Expandir relaciones relevantes.
10. Re-rankear con relaciones.
11. Seleccionar chunks finales con diversidad por entidad para comparaciones y combinaciones.
12. Construir `GroundedContextPackage`.
13. Ensamblar respuesta grounded deterministica.
14. Entregar `StudyRecommendationResult`.

Salida:

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

## 5. Fase A: Ingestion Sin DB

Objetivo:

- validar el corpus;
- normalizar IDs y senales;
- generar chunks reproducibles;
- extraer relaciones sin tocar base de datos.

Archivos principales:

- `src/schemas/rag.py`
- `src/rag/ingestion/contracts.py`
- `src/rag/ingestion/frontmatter.py`
- `src/rag/ingestion/normalization.py`
- `src/rag/ingestion/validation.py`
- `src/rag/ingestion/chunking.py`
- `src/rag/ingestion/relations.py`
- `src/rag/ingestion/pipeline.py`
- `scripts/build_rag_corpus.py`

Artefactos generados:

- `knowledge_base/study_recommendations/manifests/document_inventory.json`
- `knowledge_base/study_recommendations/manifests/chunk_manifest.json`
- `knowledge_base/study_recommendations/manifests/relation_manifest.json`
- `knowledge_base/study_recommendations/processed/chunks/chunks.jsonl`

Decisiones importantes:

- `recuperacion_activa` se normaliza a `active_recall`.
- Las senales del corpus en espanol se normalizan a las senales usadas por el codigo.
- El chunking se hace por estructura Markdown, no por cortes arbitrarios.
- Las relaciones se extraen como edges ligeros, no como grafo externo.

Pruebas asociadas:

- `tests/test_rag_ingestion_contract.py`
- `tests/test_rag_normalization.py`
- `tests/test_rag_chunking.py`
- `tests/test_rag_relations.py`

Resultado:

- Corpus validado sin errores.
- Chunks y manifests reproducibles.
- Relaciones explicitas disponibles para retrieval y rerank.

## 6. Fase B: Persistencia PostgreSQL + pgvector

Objetivo:

- crear persistencia del corpus en schema separado `rag`;
- habilitar busqueda lexical y vectorial;
- mantener embeddings si el chunk no cambio;
- limpiar o invalidar embeddings si el checksum cambia.

Archivos principales:

- `migrations/0016_rag_study_recommendations.sql`
- `src/repositories/rag/repository.py`
- `src/repositories/rag/__init__.py`

Tablas creadas:

- `rag.ingestion_runs`
- `rag.documents`
- `rag.chunks`
- `rag.relations`

Indices relevantes:

- indices B-tree para filtros;
- GIN sobre `content_tsv`;
- HNSW sobre `embedding vector_cosine_ops`.

Detalle critico corregido:

```sql
embedding VECTOR(1536) NULL
```

Esto corrige el error inicial:

```text
ERROR: column does not have dimensions
```

Ese error ocurria porque el indice HNSW de pgvector requiere dimension fija. La migracion ahora define dimension 1536, alineada con `text-embedding-3-small` / Azure deployment usado.

Pruebas asociadas:

- `tests/test_rag_repository.py`

Resultado:

- Persistencia desacoplada en schema `rag`.
- Upsert idempotente.
- Preservacion de embeddings por checksum.
- Busqueda lexical y vectorial expuestas por contrato de repositorio.

## 7. Fase C: Embeddings

Objetivo:

- generar embeddings incrementalmente;
- soportar Azure OpenAI para embeddings;
- mantener proveedor aislado en `integrations`.

Archivos principales:

- `src/integrations/embeddings/client.py`
- `src/integrations/embeddings/openai_client.py`
- `src/rag/ingestion/embedding_pipeline.py`
- `src/bootstrap/settings.py`

Variables soportadas:

```text
AZURE_OPENAI_API_KEY_EMBEDDINGS
AZURE_OPENAI_ENDPOINT_EMBEDDINGS
AZURE_OPENAI_DEPLOYMENT_NAME_EMBEDDINGS
OPENAI_API_VERSION_EMBEDDINGS
RAG_EMBEDDING_PROVIDER
RAG_EMBEDDING_MODEL
RAG_EMBEDDING_DIMENSIONS
```

Comportamiento:

- Si existen variables Azure de embeddings, el provider se infiere como `azure_openai`.
- Se pueden usar endpoints Azure completos o endpoint base del recurso.
- `embed_changed_chunks` solo procesa chunks sin embedding o con checksum nuevo.

Pruebas asociadas:

- `tests/test_embedding_clients.py`
- `tests/test_rag_embedding_pipeline.py`
- `tests/test_bootstrap_container.py`

Resultado:

- Cliente Azure/OpenAI aislado de la logica del agente.
- Pipeline incremental funcional.
- Base de datos quedo con embeddings completos segun el proceso ejecutado por el usuario.

## 8. Fase D: Retrieval Hibrido

Objetivo:

- implementar recuperacion hibrida con filtros estructurales;
- combinar lexical + vectorial;
- rerankear con reglas de dominio;
- usar relaciones explicitas sin GraphRAG completo.

Archivos principales:

- `src/rag/retrieval/models.py`
- `src/rag/retrieval/query.py`
- `src/rag/retrieval/filters.py`
- `src/rag/retrieval/hybrid.py`
- `src/rag/retrieval/rerank.py`
- `src/rag/retrieval/relations.py`
- `src/rag/retrieval/context.py`

Intenciones soportadas:

- `explain_technique`
- `recommend_technique`
- `recommend_method`
- `compare_options`
- `technique_vs_method`
- `combine_techniques`
- `adapt_method`
- `session_guidance`
- `contraindication_check`

Hardening agregado en Fase H sobre esta fase:

- `PRIMARY_TECHNIQUES_BY_SIGNAL` en `query.py`, para mapear senales a tecnica primaria cuando la consulta no menciona tecnica explicita.
- Seleccion diversa por entidad en `hybrid.py`, para que comparaciones y combinaciones no devuelvan solo chunks de una entidad.

Pruebas asociadas:

- `tests/test_rag_retrieval_query.py`
- `tests/test_rag_rerank.py`
- `tests/test_rag_hybrid_retrieval.py`

Resultado:

- Retrieval hibrido estable.
- Degradacion controlada de filtros.
- Relaciones usadas para ranking y cautelas.
- Mejor cobertura en comparaciones y recomendaciones por senal.

## 9. Fase E: Prompting Grounded

Objetivo:

- convertir contexto recuperado en respuesta breve, estructurada y auditable;
- evitar alucinacion;
- bloquear combinaciones contraindicadas;
- devolver fallback honesto si no hay fuentes.

Archivos principales:

- `src/rag/prompting/context_package.py`
- `src/rag/prompting/templates.py`
- `src/rag/prompting/grounded_answer.py`
- `src/rag/prompting/__init__.py`

Comportamiento:

- Selecciona un chunk primario.
- Extrae hechos de soporte.
- Extrae cautelas desde relaciones o chunks de contraindicacion.
- Construye `recommended_techniques`, `recommended_methods`, `combinations`.
- Llena `source_chunks`, `relations_used` y `groundedness_notes`.
- Renderiza respuestas deterministicas y cortas.

Hardening agregado:

- Las relaciones `recommended_with` ya no expanden combinaciones en preguntas explicativas o recomendaciones simples.
- `supports_signal` y `best_for_activity` solo agregan payload si la entidad fuente ya fue seleccionada.
- Esto evita recomendar tecnicas perifericas solo porque comparten una senal general.

Pruebas asociadas:

- `tests/test_rag_grounded_prompting.py`

Resultado:

- Respuestas grounded.
- Fallback controlado.
- Contraindicaciones explicitas respetadas.
- Menor riesgo de sobre-recomendacion.

## 10. Fase F: Servicio `study_recommendations`

Objetivo:

- crear una frontera de negocio para que el agente use RAG sin conocer detalles de retrieval, DB ni embeddings.

Archivos principales:

- `src/services/study_recommendations/models.py`
- `src/services/study_recommendations/service.py`
- `src/services/study_recommendations/__init__.py`
- `src/bootstrap/container.py`
- `src/agents/support/dependencies.py`

Metodos del servicio:

- `answer_query`
- `explain_technique`
- `recommend_for_student`
- `recommend_for_session`
- `adapt_method_for_subject`
- `validate_technique_combination`
- `is_study_recommendation_message`

Comportamiento:

- Si `RAG_ENABLED=false`, retorna fallback estructurado.
- Si falta configuracion, retorna fallback estructurado.
- Si retrieval falla en runtime, no rompe el flujo del agente.
- Construye DTOs estrechos, no pasa `AgentState` completo.

Pruebas asociadas:

- `tests/test_study_recommendation_service.py`
- `tests/test_bootstrap_container.py`

Resultado:

- Servicio listo para consumo del agente.
- Fallos del RAG encapsulados.
- Arquitectura por capas mantenida.

## 11. Fase G: Integracion Controlada Con El Agente

Objetivo:

- conectar el RAG en puntos pequenos y reversibles;
- no reemplazar Radar, planner ni replanning.

Integraciones implementadas:

### 11.1 Complemento En Resumen De Personalizacion

Archivo:

- `src/agents/support/nodes/persist_study_profile/node.py`

Uso:

- Agrega complemento pedagogico si el servicio RAG esta listo y trae fuentes.
- Si el servicio no esta listo, mantiene el resumen base.

### 11.2 Guia De Primera Sesion En Plan Semanal

Archivos:

- `src/agents/support/nodes/build_study_plan/node.py`
- `src/agents/support/planning/formatter.py`

Uso:

- Agrega `rag_session_guidance` dentro de `study_plan.rules`.
- No modifica eventos, horarios, restricciones ni asignacion del planner.
- El formatter lo convierte en una guia breve para el usuario.

### 11.3 Preguntas Directas Sobre Tecnicas Y Metodos

Archivos:

- `src/agents/support/nodes/answer_study_recommendation/node.py`
- `src/agents/support/nodes/answer_study_recommendation/__init__.py`
- `src/agents/support/agent.py`

Uso:

- Si el usuario pregunta directamente por tecnicas/metodos, se enruta al nodo `answer_study_recommendation`.
- Actualizaciones academicas y reparaciones de horario mantienen prioridad.
- El nodo construye `StudyRecommendationQuery` y llama al servicio.

Pruebas asociadas:

- `tests/test_study_planning_service.py`
- `tests/test_study_recommendation_agent_flow.py`

Resultado:

- Integracion segura y pequena.
- El agente sigue desacoplado de detalles RAG.
- No se conecto RAG a replanning.

## 12. Fase H: Evaluacion Y Hardening

Objetivo:

- medir calidad antes de produccion;
- crear dataset reproducible;
- detectar regresiones;
- validar fallbacks, groundedness, contraindicaciones y latencia.

Archivos principales:

- `src/rag/evaluation/models.py`
- `src/rag/evaluation/runner.py`
- `src/rag/evaluation/__init__.py`
- `scripts/evaluate_rag.py`
- `knowledge_base/study_recommendations/processed/evals/study_recommendation_eval_dataset.jsonl`
- `knowledge_base/study_recommendations/processed/evals/README.md`
- `.gitignore`

### 12.1 Para Que Era El Dataset

El dataset no es corpus fuente. Es un set de evaluacion curado para comprobar que el RAG recupera y responde correctamente.

Sirve para:

- medir Recall@k de entidades esperadas;
- medir MRR;
- medir cobertura de `chunk_kind`;
- detectar entidades prohibidas;
- detectar terminos prohibidos en respuesta;
- comprobar que las respuestas tengan fuentes internas;
- comprobar contraindicaciones;
- comprobar que `RAG_ENABLED=false` produzca fallback seguro;
- medir latencia local del pipeline;
- proteger el sistema contra regresiones futuras.

El dataset tiene 70 casos:

- 10 definiciones;
- 10 recomendaciones de tecnica;
- 10 recomendaciones de metodo;
- 10 comparaciones;
- 10 consultas con restricciones de materia/actividad;
- 10 casos negativos;
- 10 combinaciones de tecnicas.

Cada caso define, segun aplique:

- `eval_id`
- `category`
- `query`
- `intent`
- `student_signals`
- `top_techniques`
- `subject_name`
- `subject_type`
- `activity_type`
- `expected_entities`
- `expected_chunk_kinds`
- `expected_relation_types`
- `expected_answer_terms`
- `forbidden_entities`
- `forbidden_answer_terms`
- `require_sources`
- `expect_caution`
- `notes`

### 12.2 Runner De Evaluacion

El runner soporta dos backends:

```text
local
postgres
```

Backend `local`:

- construye el corpus en memoria;
- usa `InMemoryRagRepository`;
- usa embeddings deterministicos `hash-bow`;
- no consume red ni Azure;
- sirve para CI y regresiones rapidas.

Backend `postgres`:

- usa PostgreSQL real;
- usa pgvector real;
- usa provider de embeddings configurado;
- sirve para validar la calidad real con embeddings persistidos.

Comando local:

```bash
uv run python scripts/evaluate_rag.py --check-disabled-fallback --fail-under-entity-recall 0.95 --fail-under-groundedness 1.0 --fail-on-forbidden
```

Comando PostgreSQL recomendado:

```bash
uv run python scripts/evaluate_rag.py --backend postgres --check-disabled-fallback --output knowledge_base/study_recommendations/processed/evals/reports/postgres_report.json --fail-under-entity-recall 0.95 --fail-under-groundedness 1.0 --fail-on-forbidden
```

Los reportes se escriben en:

```text
knowledge_base/study_recommendations/processed/evals/reports/
```

Ese directorio esta ignorado por git para no versionar salidas generadas.

### 12.3 Resultados Actuales De Evaluacion Local

Resultado ejecutado durante esta revision:

```text
cases: 70
passed: 70
pass_rate: 1.000
entity_recall_at_k: 1.000
entity_precision_at_k: 0.675
mrr: 1.000
chunk_kind_recall: 0.695
groundedness_rate: 1.000
caution_success_rate: 1.000
forbidden_entity_violations: 0
forbidden_answer_term_violations: 0
disabled_fallback: 70/70
```

Interpretacion:

- Todas las preguntas del dataset pasan.
- Las entidades esperadas se recuperan en los casos que declaran entidades.
- No hay recomendaciones que violen entidades prohibidas.
- No hay terminos prohibidos en respuestas.
- Todas las respuestas activas tienen fuentes.
- El fallback con RAG deshabilitado funciona correctamente.

## 13. Verificacion Tecnica Realizada

### 13.1 Validacion Del Corpus

Comando ejecutado:

```bash
uv run python scripts/build_rag_corpus.py --validate-only
```

Resultado:

```text
documents: 15
chunks: 468
relations: 355
issues: 0
```

### 13.2 Evaluacion RAG Local

Comando ejecutado:

```bash
uv run python scripts/evaluate_rag.py --check-disabled-fallback --fail-under-entity-recall 0.95 --fail-under-groundedness 1.0 --fail-on-forbidden
```

Resultado:

```text
70/70 casos pasan
groundedness_rate: 1.000
forbidden_entity_violations: 0
disabled_fallback: 70/70
```

### 13.3 Pruebas Automatizadas

Suite completa ejecutada:

```bash
uv run pytest
```

Resultado:

```text
388 passed
```

### 13.4 Check Arquitectonico

Se verifico que `src/agents/support` no importe directamente:

- `rag`
- `repositories.rag`
- `integrations.embeddings`

Resultado:

```text
sin importaciones directas encontradas
```

Esto confirma que la integracion pasa por `services/study_recommendations`.

## 14. Revision De Calidad De Implementacion

### 14.1 Lo Que Quedo Bien

La implementacion esta alineada con el plan por estas razones:

- usa RAG hibrido, no GraphRAG innecesario;
- mantiene corpus fuera de `src`;
- separa ingestion, retrieval, prompting, evaluation, repositorio, integracion y servicio;
- usa DTOs estables;
- no pasa `AgentState` completo al RAG;
- preserva el Radar y planner deterministico;
- usa schema `rag` separado;
- mantiene embeddings incrementales por checksum;
- usa fallback en fallos de configuracion o runtime;
- tiene pruebas por capa;
- tiene evals curadas para medir calidad;
- tiene hardening contra recomendaciones perifericas y contraindicaciones.

### 14.2 Mejoras Aplicadas Durante Hardening

La Fase H encontro y corrigio problemas reales:

- comparaciones que podian recuperar solo una entidad;
- recomendaciones que podian expandir relaciones demasiado;
- consultas por senal que no siempre llegaban a la tecnica primaria;
- payload de recomendaciones contaminado por relaciones `supports_signal` de entidades no seleccionadas.

Correcciones:

- diversidad por entidad en `HybridRagRetriever`;
- mapeo senal -> tecnica primaria en `understand_query`;
- restriccion de expansion de relaciones en `context_package`;
- dataset ajustado para reflejar evidencia real cuando un chunk `agent_guidance` era el mejor resultado valido.

### 14.3 Riesgos Controlados

Riesgo: RAG rompe flujos del agente.

Control:

- servicio intermedio;
- fallbacks;
- pruebas de flujo;
- suite completa pasa.

Riesgo: respuestas no grounded.

Control:

- `source_chunks` obligatorio en evals;
- fallback si no hay chunks;
- `groundedness_notes`;
- eval `groundedness_rate`.

Riesgo: contraindicaciones ignoradas.

Control:

- relaciones `contraindicated_with`;
- cautions;
- evals negativas;
- `fail-on-forbidden`.

Riesgo: recomendaciones demasiado amplias.

Control:

- payload restringido a entidades seleccionadas;
- expansion de relaciones limitada;
- diversidad por entidad solo en intenciones multi-entidad.

Riesgo: dependencia de Azure/OpenAI.

Control:

- cliente aislado en `integrations`;
- backend local de eval sin red;
- fallback si proveedor falla.

## 15. Archivos Creados O Modificados Por Area

### 15.1 Contratos

- `src/schemas/rag.py`
- `src/schemas/__init__.py`

### 15.2 Ingestion

- `src/rag/ingestion/contracts.py`
- `src/rag/ingestion/frontmatter.py`
- `src/rag/ingestion/normalization.py`
- `src/rag/ingestion/validation.py`
- `src/rag/ingestion/chunking.py`
- `src/rag/ingestion/relations.py`
- `src/rag/ingestion/pipeline.py`
- `src/rag/ingestion/embedding_pipeline.py`
- `src/rag/ingestion/__init__.py`

### 15.3 Retrieval

- `src/rag/retrieval/models.py`
- `src/rag/retrieval/query.py`
- `src/rag/retrieval/filters.py`
- `src/rag/retrieval/relations.py`
- `src/rag/retrieval/rerank.py`
- `src/rag/retrieval/context.py`
- `src/rag/retrieval/hybrid.py`
- `src/rag/retrieval/__init__.py`

### 15.4 Prompting

- `src/rag/prompting/context_package.py`
- `src/rag/prompting/templates.py`
- `src/rag/prompting/grounded_answer.py`
- `src/rag/prompting/__init__.py`

### 15.5 Evaluacion

- `src/rag/evaluation/models.py`
- `src/rag/evaluation/runner.py`
- `src/rag/evaluation/__init__.py`
- `scripts/evaluate_rag.py`
- `knowledge_base/study_recommendations/processed/evals/study_recommendation_eval_dataset.jsonl`
- `knowledge_base/study_recommendations/processed/evals/README.md`

### 15.6 Persistencia

- `migrations/0016_rag_study_recommendations.sql`
- `src/repositories/rag/repository.py`
- `src/repositories/rag/__init__.py`
- `src/repositories/__init__.py`

### 15.7 Embeddings

- `src/integrations/embeddings/client.py`
- `src/integrations/embeddings/openai_client.py`
- `src/integrations/embeddings/__init__.py`
- `src/bootstrap/settings.py`

### 15.8 Servicio

- `src/services/study_recommendations/models.py`
- `src/services/study_recommendations/service.py`
- `src/services/study_recommendations/__init__.py`
- `src/bootstrap/container.py`
- `src/agents/support/dependencies.py`

### 15.9 Integracion Con Agente

- `src/agents/support/agent.py`
- `src/agents/support/nodes/persist_study_profile/node.py`
- `src/agents/support/nodes/build_study_plan/node.py`
- `src/agents/support/nodes/answer_study_recommendation/node.py`
- `src/agents/support/nodes/answer_study_recommendation/__init__.py`
- `src/agents/support/planning/formatter.py`

### 15.10 Scripts Y Artefactos

- `scripts/build_rag_corpus.py`
- `scripts/evaluate_rag.py`
- `knowledge_base/study_recommendations/manifests/document_inventory.json`
- `knowledge_base/study_recommendations/manifests/chunk_manifest.json`
- `knowledge_base/study_recommendations/manifests/relation_manifest.json`
- `knowledge_base/study_recommendations/processed/chunks/chunks.jsonl`
- `.gitignore`
- `src/rag/README.md`

### 15.11 Tests

- `tests/test_rag_ingestion_contract.py`
- `tests/test_rag_normalization.py`
- `tests/test_rag_chunking.py`
- `tests/test_rag_relations.py`
- `tests/test_rag_repository.py`
- `tests/test_embedding_clients.py`
- `tests/test_rag_embedding_pipeline.py`
- `tests/test_rag_retrieval_query.py`
- `tests/test_rag_rerank.py`
- `tests/test_rag_hybrid_retrieval.py`
- `tests/test_rag_grounded_prompting.py`
- `tests/test_rag_evaluation.py`
- `tests/test_study_recommendation_service.py`
- `tests/test_study_recommendation_agent_flow.py`
- `tests/test_study_planning_service.py`
- `tests/test_bootstrap_container.py`

## 16. Comandos Operativos Recomendados

Validar corpus:

```bash
uv run python scripts/build_rag_corpus.py --validate-only
```

Regenerar artefactos:

```bash
uv run python scripts/build_rag_corpus.py --write-artifacts
```

Sincronizar DB:

```bash
uv run python scripts/build_rag_corpus.py --sync-db
```

Generar embeddings faltantes:

```bash
uv run python scripts/build_rag_corpus.py --embed-changed
```

Evaluar local:

```bash
uv run python scripts/evaluate_rag.py --check-disabled-fallback --fail-under-entity-recall 0.95 --fail-under-groundedness 1.0 --fail-on-forbidden
```

Evaluar PostgreSQL real:

```bash
uv run python scripts/evaluate_rag.py --backend postgres --check-disabled-fallback --output knowledge_base/study_recommendations/processed/evals/reports/postgres_report.json --fail-under-entity-recall 0.95 --fail-under-groundedness 1.0 --fail-on-forbidden
```

Suite completa:

```bash
uv run pytest
```

## 17. Estado Actual Y Pendientes

Estado actual:

- Fases A-H implementadas.
- Corpus valido.
- Evals locales pasan 70/70.
- Suite completa pasa.
- Arquitectura por capas respetada.
- Fallback con `RAG_ENABLED=false` validado.

Pendiente recomendado antes de activar en produccion:

- ejecutar `scripts/evaluate_rag.py --backend postgres` contra la DB real con pgvector y embeddings Azure;
- revisar latencia real con provider de embeddings;
- activar `RAG_ENABLED=true` solo despues de pasar esa evaluacion;
- guardar el reporte de PostgreSQL como evidencia local, sin versionar `reports/`.

No se recomienda todavia:

- conectar RAG a replanning automatico;
- usar RAG para reemplazar scoring de personalizacion;
- aumentar integraciones en el grafo antes de medir backend PostgreSQL.

## 18. Conclusion

La implementacion desde la Fase A hasta la Fase H quedo alineada con el plan, con la arquitectura del agente y con el objetivo del MVP. La solucion evita complejidad innecesaria, mantiene boundaries limpios, conserva la logica deterministica del agente y agrega una capa RAG medible, auditable y tolerante a fallos.

Desde el punto de vista tecnico, la implementacion esta en buen estado para el siguiente paso: evaluacion real con PostgreSQL + pgvector + Azure embeddings y rollout controlado con `RAG_ENABLED=true` si esa evaluacion pasa.
