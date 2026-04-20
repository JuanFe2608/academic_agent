# Fase 13 - Dispatch WhatsApp De Recordatorios

## Objetivo

Enviar recordatorios vencidos por WhatsApp usando la cola durable de `reminder_dispatches`, sin duplicar envios y registrando fallos para reintento operativo.

## Logica aplicada

1. `ReminderDispatchRunner` toma dispatches vencidos con leasing.
2. Cada canal usa un sender explicito:
   - `in_app`: marca localmente como enviado.
   - `email`: usa Microsoft Graph cuando esta configurado.
   - `whatsapp`: usa `WhatsAppChannelService` y `WhatsAppCloudClient`.
3. El mensaje WhatsApp se renderiza segun el tipo:
   - `pre_session`: aviso antes de estudiar.
   - `followup`: pregunta por avance al terminar.
   - `missed_session`: pide confirmacion para replanificar.
4. El destinatario WhatsApp se resuelve en este orden:
   - payload del dispatch: `whatsapp_recipient_id`, `recipient_id`, `to`, `phone_number`, `conversation_id` o `sender_id`;
   - `ACADEMIC_AGENT_WHATSAPP_RECIPIENTS`;
   - `ACADEMIC_AGENT_DEFAULT_WHATSAPP_RECIPIENT_ID`.
5. Si WhatsApp falla con error temporal, el dispatch queda `retryable` y `next_attempt_at`.
6. Si se agotan intentos o falta destinatario, el dispatch queda `failed`.
7. Un dispatch `sent`, `failed` o `retryable` no vuelve a enviarse inmediatamente como `pending`, evitando duplicados.

## Variables operativas

```bash
export ACADEMIC_AGENT_ENABLE_STUDY_PLAN_MATERIALIZATION=1
export ACADEMIC_AGENT_REMINDER_CHANNELS=whatsapp
export WHATSAPP_ACCESS_TOKEN="..."
export WHATSAPP_PHONE_NUMBER_ID="..."
export ACADEMIC_AGENT_WHATSAPP_RECIPIENTS='{"15":"573001112233"}'
```

Opcionales:

```bash
export ACADEMIC_AGENT_REMINDER_DISPATCH_MAX_ATTEMPTS=3
export ACADEMIC_AGENT_REMINDER_RETRY_DELAY_MINUTES=15
```

## Comando operativo

```bash
uv run python scripts/run_due_reminders.py --limit 20
```

Para pruebas controladas:

```bash
uv run python scripts/run_due_reminders.py --limit 20 --as-of 2026-01-05T08:00:00-05:00
```

## Migracion

Se agrego `migrations/0020_reminder_dispatch_retry.sql` para soportar:

- `attempt_count`;
- `next_attempt_at`;
- estado `retryable`;
- indice de dispatches reintentables.

## Pruebas

```bash
uv run --with pytest python -m pytest tests/test_reminder_dispatch_service.py tests/test_whatsapp_channel_service.py
```

## Nota arquitectonica

La fase queda fuera del grafo conversacional. El grafo solo materializa y agenda recordatorios; el worker operativo los entrega por canal. Esto mantiene separadas la conversacion, la planificacion y la infraestructura de delivery.
