# Study Recommendations Corpus

Coleccion fuente para el RAG de recomendaciones academicas.

Estructura:

- `raw/frameworks/`
  Marcos conceptuales o de decision. No son metodos operativos, pero ayudan a clasificar consultas y a decidir entre tecnica aislada vs metodo completo.
- `raw/matrices/`
  Matrices de combinacion y comparacion. Sirven para retrieval comparativo, composicion de recomendaciones y filtros por compatibilidad.
- `raw/methods/`
  Metodos de estudio completos. Suelen combinar varias tecnicas, fases y adaptaciones.
- `raw/techniques/`
  Tecnicas puntuales de estudio. Son unidades operativas mas pequeñas y reusables.
- `manifests/`
  Inventarios del corpus, manifests de chunking, checksums y metadata derivada.
- `processed/chunks/`
  Artefactos intermedios reproducibles del chunking.
- `processed/evals/`
  Preguntas, goldens y resultados de evaluacion del retrieval.

Reglas:

- `raw/` es la fuente canonica.
- Los chunks, embeddings y manifests se regeneran; no son la fuente de verdad.
- La organizacion fisica debe coincidir con el `knowledge_type` o `document_type` del frontmatter.
- Si un documento cambia de tipo semantico, primero se corrige el frontmatter y luego su ubicacion.

Contrato minimo esperado por documento:

- frontmatter YAML al inicio;
- identificador estable (`technique_id`, `method_id`, `framework_id` o `matrix_id`);
- `knowledge_type`;
- `name`;
- `status`;
- `version`;
- headings Markdown consistentes;
- seccion reutilizable para respuestas grounded, idealmente `Respuesta corta reusable para RAG` y/o `Respuesta larga reusable para RAG`.
