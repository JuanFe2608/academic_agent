# Capa RAG

Esta carpeta no debe mezclar persistencia operativa ni lógica conversacional.

Subcapas reservadas:

- `ingestion/`: carga, chunking, embeddings y versionado de conocimiento.
- `retrieval/`: búsqueda, ranking y composición de contexto.
- `prompting/`: plantillas y ensamblaje grounded para consumo desde servicios.
