# Refactor Arquitectura - Fase 8

Fecha: 2026-04-03

## Objetivo ejecutado

Se cerró la fase de enforcement arquitectónico y documentación final para evitar recaídas del refactor.

## Cambios implementados

- se agregaron guardrails de frontera de capas para validar que `agents/` no importe `repositories/` ni `integrations/` directamente, salvo wrappers de compatibilidad explícitos;
- se reforzó la protección sobre `schemas/`, `state.py` y la zona `src/agents/support/tools/`;
- se eliminaron acoples directos de `agents/` hacia `integrations/ai` y `repositories/onboarding` mediante wrappers válidos en `services/`;
- se consolidó la documentación de arquitectura en `README.md` y `docs/architecture_rules.md`;
- se preparó estructura inicial para líneas futuras en `src/rag/` y `src/integrations/whatsapp/`.

## Ajustes de capa realizados

- `services/scheduling/ai_support.py` concentra acceso AI de dominio scheduling;
- `services/scheduling/activity_matching.py` pasa a ser el origen real del matching de actividades;
- `agents/support/tools/activity_matching.py` queda como wrapper de compatibilidad;
- nodos de verificación de correo dejan de importar errores de repositorio directamente.

## Enforcement añadido

- `agents/` productivo sin imports directos a `repositories/` ni `integrations/`;
- `schemas/` aislado de capas superiores;
- `tools/` congelado con allowlist explícita;
- `state.py` restringido a `services.scheduling.validation` como única dependencia de `services/`;
- placeholders obligatorios para `rag/` y `integrations/whatsapp/`.

## Salida de la fase

- la arquitectura queda documentada en un punto de entrada visible para el equipo;
- las reglas críticas ya están automatizadas;
- el repo queda listo para abrir RAG y canales futuros sin reintroducir zonas grises.
