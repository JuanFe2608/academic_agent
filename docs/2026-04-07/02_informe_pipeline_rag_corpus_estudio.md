# Informe Del Pipeline RAG Para El Corpus De Estudio

Fecha: 2026-04-07

Estado: propuesta operativa y validacion inicial del corpus

## 1. Objetivo

Definir el pipeline recomendado para construir un RAG de alta calidad para este proyecto a partir de los documentos Markdown ya cargados en `knowledge_base/`, sin contaminar el core operacional del agente.

## 2. Revision Del Corpus Actual

### 2.1 Estado observado

Se detectaron 15 documentos Markdown en el corpus, con una estructura apta para ingestion controlada:

- 8 tecnicas;
- 4 metodos operativos;
- 2 frameworks;
- 1 matriz de combinacion.

Volumen aproximado actual:

- 6026 lineas totales de corpus.

### 2.2 Fortalezas del corpus

Los documentos ya tienen las dos piezas mas importantes para un buen RAG:

1. frontmatter YAML con metadata semantica rica;
2. estructura jerarquica en Markdown con secciones altamente reusables.

Campos observados de valor para retrieval:

- `knowledge_type`
- identificadores estables por tipo (`technique_id`, `method_id`, `framework_id`, `matrix_id`)
- `objective_types`
- `best_for_activity_types`
- `best_for_subject_types`
- `best_for_student_profiles`
- `best_for_signals`
- `recommended_combinations`
- `contraindicated_combinations`
- `evidence_level`
- `confidence_level`
- `tags`

Secciones observadas de alto valor para chunking:

- `Definición breve`
- `Objetivo principal`
- `Para qué sirve`
- `Para qué no sirve tanto`
- `Señales de que conviene`
- `Señales de que no conviene`
- `Combinaciones recomendadas`
- `Errores comunes`
- `Recomendación operativa para el agente`
- `Respuesta corta reusable para RAG`
- `Respuesta larga reusable para RAG`
- `Metadatos de recuperación sugeridos`

### 2.3 Problemas detectados

1. La carpeta `study_tecniques/` tenia un typo.
2. `study_methods/` mezclaba metodos, frameworks y matrices en la misma ruta.
3. `marco_decision_tecnica_vs_metodo_de_estudio.md` estaba etiquetado como `study_method`, aunque semanticamente funciona como framework de decision.

## 3. Ajustes Realizados

Se reorganizo el corpus bajo una sola coleccion:

```text
knowledge_base/
  study_recommendations/
    raw/
      frameworks/
      matrices/
      methods/
      techniques/
    manifests/
    processed/
      chunks/
      evals/
```

Cambios aplicados:

- se unifico el corpus en `knowledge_base/study_recommendations/`;
- se corrigio la separacion fisica por tipo de conocimiento;
- se corrigio el typo estructural eliminando `study_tecniques/`;
- se normalizo el frontmatter de `marco_decision_tecnica_vs_metodo_de_estudio.md` para tratarlo como framework.

## 4. Lectura Arquitectonica

Este corpus no debe usarse como un RAG generico de "buscar texto parecido y responder".

Por la estructura de los documentos, el mejor enfoque para este proyecto es:

`RAG orientado por tipo de conocimiento + filtros semanticos + ensamblaje grounded`

Eso implica:

- primero clasificar la necesidad de la consulta;
- luego recuperar desde el subconjunto correcto del corpus;
- por ultimo ensamblar una respuesta grounded con chunks de alta precision.

## 5. Pipeline Recomendado

## 5.1 Fase 0. Contrato del corpus

Antes de vectorizar, el pipeline debe validar:

- que cada archivo tenga frontmatter;
- que el frontmatter tenga `knowledge_type` e identificador estable;
- que exista `name`, `status` y `version`;
- que el documento tenga al menos un `#` principal y varios `##`;
- que no haya conflicto entre tipo semantico y ruta fisica.

Salida:

- `document_inventory.json` o equivalente en `manifests/`;
- checksums por archivo;
- errores de validacion si un documento no cumple contrato.

## 5.2 Fase 1. Normalizacion de metadata

El loader debe transformar el frontmatter a un contrato normalizado comun.

Contrato normalizado sugerido por documento:

- `document_id`
- `knowledge_type`
- `document_type`
- `name`
- `aliases`
- `status`
- `version`
- `source_path`
- `checksum`
- `activity_types`
- `subject_types`
- `student_profiles`
- `signals`
- `evidence_level`
- `confidence_level`
- `tags`

Regla importante:

- el pipeline debe homogenizar singular/plural y campos equivalentes del corpus;
- no debe depender ciegamente del nombre original del campo.

## 5.3 Fase 2. Chunking estructural

El chunking recomendado no es por tamaño fijo.

La estrategia correcta para este corpus es:

### Nivel A. Chunk semantico por seccion

Unidad base:

- un bloque `##` completo;
- o un `##` con sus `###` hijas cuando la seccion sea una familia de variantes.

### Nivel B. Chunk especializado por tipo de documento

#### Tecnicas

Chunk principal por cada `##`.

Motivo:

- las tecnicas responden bien a preguntas cortas y focalizadas como "cuando conviene", "para que no sirve", "como combinar", "errores comunes".

#### Metodos

Chunk por `##`, pero fusionando `###` de adaptacion dentro del chunk padre cuando sean parte de una misma decision:

- tiempo disponible;
- dificultad;
- tipo de actividad;
- tipo de materia.

Motivo:

- separar demasiado esos subbloques rompe la logica del metodo.

#### Frameworks

Chunk por `##`, priorizando:

- criterios de decision;
- diferencias conceptuales;
- reglas operativas;
- implicaciones para recomendacion.

Motivo:

- los frameworks sirven para routing y razonamiento, no solo para definicion.

#### Matrices

Chunk por bloque conceptual y preservar tablas completas en un mismo chunk.

Motivo:

- romper una tabla o matriz reduce mucho su utilidad para comparacion.

### Nivel C. Chunk reusable de respuesta

Crear chunks con prioridad alta para:

- `Respuesta corta reusable para RAG`
- `Respuesta larga reusable para RAG`
- `Recomendación operativa para el agente`

Estos chunks deben marcarse con flags como:

- `is_answer_ready`
- `is_agent_operational_guidance`
- `is_high_precision_summary`

## 5.4 Fase 3. Enriquecimiento de chunks

Cada chunk debe guardar metadata propia, no solo heredar la del documento.

Metadata recomendada por chunk:

- `chunk_id`
- `document_id`
- `knowledge_type`
- `document_type`
- `section_title`
- `section_level`
- `heading_path`
- `chunk_kind`
- `position_in_document`
- `token_estimate`
- `activity_types`
- `subject_types`
- `student_profiles`
- `signals`
- `evidence_level`
- `confidence_level`
- `tags`

`chunk_kind` sugeridos:

- `definition`
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

## 5.5 Fase 4. Embeddings y persistencia vectorial

La recomendacion para este repo es PostgreSQL + `pgvector`, pero en un area separada del core operacional.

No conviene:

- mezclar embeddings con tablas del flujo operativo;
- usar RAG como si fuera una extension de `students`, `study_plan_*` o `schedule_*`.

Modelo sugerido:

### Schema

- `rag`

### Tablas

- `rag.documents`
- `rag.chunks`

Campos minimos recomendados:

`rag.documents`

- `id`
- `document_id`
- `knowledge_type`
- `document_type`
- `name`
- `status`
- `version`
- `source_path`
- `checksum`
- `metadata_json`
- `created_at`

`rag.chunks`

- `id`
- `chunk_id`
- `document_id`
- `knowledge_type`
- `document_type`
- `section_title`
- `heading_path`
- `chunk_kind`
- `content`
- `content_tsv`
- `metadata_json`
- `embedding`
- `created_at`

Indices recomendados:

- vector index ANN sobre `embedding`;
- GIN sobre `content_tsv` para busqueda lexical;
- indices por `knowledge_type`, `document_type`, `chunk_kind`;
- indice por `document_id`.

## 5.6 Fase 5. Retrieval

El retrieval recomendado no debe ser solo vectorial.

La mejor configuracion para este corpus es:

`query understanding -> filters -> hybrid retrieval -> rerank -> grounded assembly`

### 5.6.1 Query understanding

Clasificar cada consulta en una intencion como:

- `explain_technique`
- `recommend_technique`
- `recommend_method`
- `compare_options`
- `technique_vs_method`
- `combine_techniques`
- `adapt_method`

### 5.6.2 Filtros previos

Aplicar filtros usando metadata del query y del contexto del estudiante:

- `knowledge_type`
- `activity_type`
- `subject_type`
- `signals`
- `student_profile`
- `evidence_level`
- `confidence_level`

### 5.6.3 Hybrid retrieval

Usar dos recuperaciones:

- vectorial para semantica;
- lexical/FTS para terminos exactos como nombres de tecnica, actividad o señal.

### 5.6.4 Rerank

Rerank final con prioridad a:

1. chunks `answer_ready`;
2. chunks `agent_guidance`;
3. chunks con coincidencia fuerte en `signals` y `activity_types`;
4. chunks con mayor `confidence_level` y mejor `evidence_level`.

### 5.6.5 Ensamblaje grounded

La respuesta no debe salir de un solo chunk si la pregunta es de recomendacion.

Patrones recomendados:

- tecnica puntual:
  - `definition` + `use_case` + `contraindication` + `combination`
- metodo completo:
  - `objective` + `logic` + `steps` + `adaptation`
- comparacion:
  - `framework` + `matrix` + `answer_ready`

## 5.7 Fase 6. Prompting grounded

La capa de prompting debe vivir en `src/rag/prompting/` y no dentro del agente conversacional.

Reglas:

- siempre citar la fuente interna por `document_id` o `name`;
- separar texto recuperado de inferencia del modelo;
- impedir recomendaciones que contradigan `contraindicated_combinations` o `not_ideal_for_*` cuando la metadata sí aplica.

## 5.8 Fase 7. Evaluacion

Este corpus exige una evaluacion orientada a recuperacion util, no solo similitud semantica.

Conjuntos de evaluacion que conviene crear en `processed/evals/`:

1. preguntas de definicion;
2. preguntas de seleccion de tecnica;
3. preguntas de seleccion de metodo;
4. preguntas de comparacion tecnica vs metodo;
5. preguntas con restricciones por actividad, materia o señal;
6. preguntas negativas donde el sistema debe decir que una tecnica no conviene.

Metricas recomendadas:

- Recall@k
- Precision@k
- MRR
- groundedness
- contradiccion con metadata
- cobertura de señales del estudiante

## 6. Pipeline Ideal Por Tipos De Documento

## 6.1 Tecnicas

Uso principal:

- recomendaciones puntuales;
- explicacion breve;
- combinaciones y contraindicaciones.

Valor principal en retrieval:

- respuesta rapida;
- alta precision;
- chunks relativamente pequeños y estables.

## 6.2 Metodos

Uso principal:

- planes de estudio mas completos;
- adaptacion por tiempo, dificultad y tipo de actividad;
- recomendaciones cuando el problema es sistemico.

Valor principal en retrieval:

- respuestas mas largas;
- mas contexto;
- mas necesidad de ensamblaje multichunk.

## 6.3 Frameworks

Uso principal:

- decidir entre tecnica aislada y metodo completo;
- explicar por que el agente recomienda una intervencion y no otra;
- guiar routing del retrieval.

Valor principal en retrieval:

- capa de razonamiento y clasificacion previa.

## 6.4 Matrices

Uso principal:

- comparacion de tecnicas;
- composicion de metodos;
- apoyo a ranking de alternativas.

Valor principal en retrieval:

- comparacion estructurada;
- soporte a respuestas que requieren varias opciones.

## 7. Arquitectura Recomendada En El Repo

La mejor forma de integrarlo en este proyecto es:

```text
knowledge_base/study_recommendations/     # corpus fuente
src/rag/ingestion/                        # loaders, normalizacion, chunking
src/rag/retrieval/                        # retrieval, filtros, rerank
src/rag/prompting/                        # ensamblaje grounded
src/services/study_methods/               # frontera de negocio que consume RAG
src/repositories/rag/                     # persistencia vectorial futura
```

No conviene conectar el retrieval directamente desde `agents/support/`.

## 8. Secuencia De Implementacion Recomendada

### Paso 1

Cerrar contrato del corpus y manifests.

### Paso 2

Implementar loader de Markdown + parser de frontmatter.

### Paso 3

Implementar chunking jerarquico por tipo de documento.

### Paso 4

Generar chunks procesados y revisar manualmente una muestra.

### Paso 5

Crear migracion `pgvector` y tablas `rag.documents` / `rag.chunks`.

### Paso 6

Generar embeddings e insertar chunks.

### Paso 7

Implementar hybrid retrieval con filtros por metadata.

### Paso 8

Crear set de evaluacion con preguntas reales del agente.

### Paso 9

Abrir `src/services/study_methods/` como primera frontera de consumo.

## 9. Conclusiones

El corpus actual ya tiene base suficiente para construir un muy buen RAG porque:

- no parte de texto plano desordenado;
- tiene metadata util;
- tiene secciones explicitamente reutilizables;
- mezcla conocimiento puntual, conocimiento compuesto y marcos de decision.

La principal mejora que hacia falta antes de empezar era organizativa, no de contenido.

El siguiente paso correcto ya no es seguir moviendo carpetas, sino implementar:

1. contrato del corpus;
2. loader + normalizacion;
3. chunking estructural;
4. persistencia vectorial separada;
5. retrieval hibrido con filtros.
