# Chunks Procesados

Artefactos reproducibles del pipeline de chunking:

- documentos normalizados;
- chunks enriquecidos con metadata;
- export intermedio antes de embeddings.

## Contrato de chunking

Cada chunk debe ser una unidad recuperable, clara y auditable para embeddings,
retrieval, ranking, citacion y construccion de respuestas fundamentadas.

- `content`: contiene solo la seccion real del documento fuente. No incluye
  texto heredado de secciones anteriores o posteriores.
- `chunk_kind`: se infiere solo desde `section_title` y el contenido propio de
  la seccion.
- `retrieval_role`: define como puede usarse el chunk durante retrieval y
  prompting. No reemplaza a `chunk_kind`: `chunk_kind` describe el contenido;
  `retrieval_role` describe el comportamiento permitido.
- `checksum`: se calcula sobre `content` puro.
- `token_estimate`: se calcula sobre `content` puro.
- `metadata`: contiene fuente, senales, tipos de actividad/materia,
  recuperabilidad y navegacion estructurada (`previous_chunk_id`,
  `next_chunk_id`, `section_index`, `document_section_count`).
- contexto vecino: no se guarda dentro de `content`; se agrega despues en
  retrieval o construccion del prompt cuando haga falta.
- embeddings: se generan sobre `content` puro, sin contexto expandido.

Roles de recuperabilidad:

- `answerable`: chunk recuperable por busqueda semantica/lexica normal; puede
  entrar al prompt y recibir embedding.
- `supporting_context`: chunk no pensado como respuesta principal; puede entrar
  como contexto vecino si aporta continuidad real. Por defecto no debe competir
  en retrieval normal.
- `structured_metadata`: chunk o seccion que representa metadata operativa,
  tags o senales estructuradas. No debe competir en retrieval normal, no debe
  inyectarse como contexto vecino y no debe recibir embedding normal.

Regla explicita:

- Las secciones tituladas `Metadatos de recuperación sugeridos` se clasifican
  como `chunk_kind=metadata` y `retrieval_role=structured_metadata`.

Flags derivados esperados en `metadata`:

- `retrieval_role`
- `semantic_retrieval_enabled`
- `prompt_context_enabled`
- `embedding_enabled`

Invariantes esperadas:

- `content` empieza con su propio heading H2.
- `content` no contiene headings H2 de otras secciones.
- `chunk_kind` no cambia por contenido vecino.
- `retrieval_role` no cambia el texto de `content`; solo controla uso en
  retrieval, embeddings y prompt.
- `chunk_id` permanece estable mientras no cambien documento, posicion o titulo.
