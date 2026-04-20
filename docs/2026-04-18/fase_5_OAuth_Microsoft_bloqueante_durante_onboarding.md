Quedó integrado el gate entre correo verificado y semestre: cuando ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH=1, el
grafo entra a la fase microsoft_oauth y no continúa a pedir semestre hasta que exista conexión Microsoft
persistida. El ruteo está en src/agents/support/agent.py:124 y src/agents/support/agent.py:179.

Lo principal que quedó hecho:

- Nuevo nodo conversacional request_microsoft_oauth en src/agents/support/nodes/request_microsoft_oauth/node.py:40.
- Nuevo servicio MicrosoftOAuthFlowService para generar state aleatorio, expirable y persistido en src/services/
  sync/microsoft_oauth_flow_service.py:54.
- Handler fuera del grafo, framework-agnostic, para el callback state + code en src/services/sync/
  microsoft_oauth_callback_handler.py:24.
- Persistencia de state pendiente OAuth en el repositorio Microsoft desde src/repositories/microsoft_graph/
  state_repository.py:36.
- Persistencia anticipada de identidad mínima del estudiante antes del OAuth, y luego completado del mismo registro
  al finalizar perfil, en src/repositories/onboarding/repository.py:290.
- Estado conversacional/onboarding actualizado con microsoft_oauth e is_waiting_for_oauth.
- Migraciones nuevas:
  - migrations/0017_microsoft_oauth_onboarding_gate.sql
  - migrations/0018_grant_microsoft_oauth_pending_permissions.sql
- Pruebas nuevas del flujo en tests/test_onboarding_oauth_flow.py.

Verificación:

uv run --with pytest pytest

Resultado final: 449 passed in 112.50s.

Todo queda controlado para esta fase. La implementación mantiene la arquitectura por capas: grafo/nodo en agents,
orquestación en services, persistencia en repositories, contratos en schemas y wiring en bootstrap/dependencies.
Antes de activar el flag en un entorno real, hay que aplicar las migraciones 0017 y 0018; no las ejecuté contra la
base de datos desde aquí.
