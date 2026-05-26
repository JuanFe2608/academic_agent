# RAG Study Recommendation Evals

Este directorio contiene evaluaciones curadas para el RAG de recomendaciones de estudio.

- `study_recommendation_eval_dataset.jsonl`: dataset versionable con casos esperados.
- `baselines/`: lineas base versionables para comparar cambios grandes de
  retrieval, chunking o prompting.
- `reports/`: salidas generadas por `scripts/evaluate_rag.py`; no debe versionarse.

Comandos utiles:

```bash
PYTHONPATH=src python scripts/evaluate_rag.py
PYTHONPATH=src python scripts/evaluate_rag.py --check-disabled-fallback
PYTHONPATH=src python scripts/evaluate_rag.py --backend postgres --output knowledge_base/study_recommendations/processed/evals/reports/postgres_report.json
```

Si se escribe el comando en varias lineas, cada linea intermedia debe terminar con `\`:

```bash
PYTHONPATH=src python scripts/evaluate_rag.py \
  --backend postgres \
  --check-disabled-fallback \
  --output knowledge_base/study_recommendations/processed/evals/reports/postgres_report.json \
  --fail-under-entity-recall 0.95 \
  --fail-under-groundedness 1.0 \
  --fail-on-forbidden
```

Si `--output` apunta a un directorio, el runner escribira automaticamente `<backend>_report.json` dentro de ese directorio.

El backend `local` no usa red ni base de datos. El backend `postgres` usa PostgreSQL y el proveedor de embeddings configurado para medir el comportamiento real con `pgvector`.
