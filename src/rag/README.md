# Capa RAG

Esta carpeta no debe mezclar persistencia operativa ni lógica conversacional.

El corpus fuente no vive en `src/`. La ubicacion canonica del conocimiento fuente
para este proyecto debe estar bajo `knowledge_base/`, actualmente en:

- `knowledge_base/study_recommendations/`

Subcapas reservadas:

- `ingestion/`: carga, chunking, embeddings y versionado de conocimiento.
- `retrieval/`: búsqueda, ranking y composición de contexto.
- `prompting/`: plantillas y ensamblaje grounded para consumo desde servicios.
