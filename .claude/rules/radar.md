---
paths:
  - "src/agents/support/nodes/collect_study_profile/**/*.py"
  - "src/agents/support/personalization/**/*.py"
  - "src/services/personalization/**/*.py"
---

# Reglas para el Radar de estudio (personalización)

## Escala Likert actual

```
0 = Nunca
1 = Pocas veces
2 = Seguido
3 = Siempre
```

Aliases aceptados por el parser (ver `LIKERT_ALIASES` en `questionnaire.py`):
- 0: `"nunca"`, `"casi nunca"`, `"jamas"`
- 1: `"pocas veces"`, `"a veces"`, `"rara vez"`
- 2: `"seguido"`, `"frecuentemente"`, `"con frecuencia"`
- 3: `"siempre"`, `"casi siempre"`

## Terminología en mensajes al usuario

- Las preguntas del Radar se llaman **"Pregunta"** (no "Reto" ni "Mini reto")
- Las preguntas adicionales de desempate se llaman **"Pregunta adicional N"** (no "Reto extra N")

## Técnicas detectadas (8)

`pomodoro` · `feynman` · `active_recall` · `cornell` ·
`mapas_conceptuales` · `mnemotecnia` · `repeticion_espaciada` · `interleaving`

## Scoring

- Cada técnica se normaliza con `normalized_score = raw_score / max_score ∈ [0, 1]`
- El `max_score` depende de cuántas preguntas contribuyen a esa técnica y con qué peso
- Pomodoro e Interleaving tienen 2 preguntas primarias (max_score = 600)
- El resto tiene 1 primaria (max_score varía por secundarios)
- La normalización iguala la competencia — una técnica con más preguntas no tiene ventaja

## Desempate (tiebreaker)

Se activa si: respuestas uniformes, empate total de scores, o gap top1-top2 < 0.10.
Son 3 preguntas de opción múltiple (1–4). Cada opción hace boost a una técnica específica.

## Persistencia

```
study_personalization_profiles   ← versión activa (is_current = TRUE)
├── study_personalization_answers   ← una fila por question_id (Q01..Q10, TB01..TB03)
└── study_personalization_scores   ← una fila por técnica (8 filas)
```

`top_techniques` en el perfil es el JSONB array con los 3 IDs top — lo consume `build_study_plan`.

## Umbral de señales

Los signals se activan cuando la respuesta a la(s) pregunta(s) asociadas es `>= 2` ("Seguido").
Si se cambia la escala, este umbral necesita revisión.
