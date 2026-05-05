#!/usr/bin/env bash
# Despliega o actualiza el Container Apps Job que ejecuta el worker de
# recordatorios WhatsApp cada 5 minutos.
#
# Prerrequisitos:
#   - az login activo con permisos sobre el resource group
#   - La imagen ya construida en ACR (ejecutar 02_build_and_deploy_containerapp.sh antes)
#   - azure-pilot.env y .env con los valores correctos
#
# Uso:
#   bash scripts/deploy/03_deploy_reminder_job.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY_ENV="$ROOT_DIR/scripts/deploy/azure-pilot.env"
APP_ENV="$ROOT_DIR/.env"

fail() { printf 'ERROR: %s\n' "$1" >&2; exit 1; }
info() { printf '%s\n' "$1"; }

[[ -f "$DEPLOY_ENV" ]] || fail "No existe $DEPLOY_ENV"
[[ -f "$APP_ENV" ]]    || fail "No existe $APP_ENV"

set -a
# shellcheck source=/dev/null
source "$DEPLOY_ENV"
# shellcheck source=/dev/null
source "$APP_ENV"
set +a

# --- Validaciones mínimas para el worker de recordatorios ---
[[ -n "${ACADEMIC_AGENT_DATABASE_URL:-}" ]]        || fail "ACADEMIC_AGENT_DATABASE_URL no está definido"
[[ -n "${WHATSAPP_ACCESS_TOKEN:-}" ]]              || fail "WHATSAPP_ACCESS_TOKEN no está definido"
[[ -n "${WHATSAPP_PHONE_NUMBER_ID:-}" ]]           || fail "WHATSAPP_PHONE_NUMBER_ID no está definido"
[[ -n "${ACADEMIC_AGENT_REMINDER_WORKER_TOKEN:-}" ]] || fail "ACADEMIC_AGENT_REMINDER_WORKER_TOKEN no está definido"
[[ -n "${AZ_ACR_NAME:-}" ]]                        || fail "AZ_ACR_NAME no está definido en azure-pilot.env"
[[ -n "${AZ_CONTAINERAPPS_ENV:-}" ]]               || fail "AZ_CONTAINERAPPS_ENV no está definido en azure-pilot.env"
[[ -n "${AZ_RESOURCE_GROUP:-}" ]]                  || fail "AZ_RESOURCE_GROUP no está definido en azure-pilot.env"

command -v az >/dev/null 2>&1 || fail "Azure CLI no instalado o no está en PATH"
az account show >/dev/null 2>&1 || fail "Azure CLI sin sesión activa. Ejecuta: az login"

az extension add --name containerapp --upgrade --only-show-errors >/dev/null

AZ_REMINDER_JOB_NAME="${AZ_REMINDER_JOB_NAME:-caj-lara-reminder-worker-pilot}"
IMAGE_REF="$AZ_ACR_NAME.azurecr.io/$AZ_IMAGE_NAME:$AZ_IMAGE_TAG"

# Cron: cada 5 minutos. Ajustar si se quiere otro intervalo.
CRON_SCHEDULE="${AZ_REMINDER_JOB_CRON:-*/5 * * * *}"

# Máximo tiempo por ejecución: 2 minutos. Con limit=500 y una BD normal
# un lote completa en segundos, así que 120s es amplio.
REPLICA_TIMEOUT="${AZ_REMINDER_JOB_TIMEOUT:-120}"

info "== Obteniendo credenciales ACR =="
ACR_PASSWORD="$(az acr credential show --name "$AZ_ACR_NAME" --query 'passwords[0].value' -o tsv)"

# Secretos que necesita el worker de recordatorios.
# Intencionalmente mínimos: no incluye claves de OpenAI ni Microsoft OAuth.
SECRETS=(
  "reminder-db-url=${ACADEMIC_AGENT_DATABASE_URL}"
  "reminder-whatsapp-token=${WHATSAPP_ACCESS_TOKEN}"
  "reminder-worker-token=${ACADEMIC_AGENT_REMINDER_WORKER_TOKEN}"
)

# Variables de entorno del worker.
ENV_VARS=(
  "ACADEMIC_AGENT_DATABASE_URL=secretref:reminder-db-url"
  "WHATSAPP_ACCESS_TOKEN=secretref:reminder-whatsapp-token"
  "ACADEMIC_AGENT_REMINDER_WORKER_TOKEN=secretref:reminder-worker-token"
  "WHATSAPP_PHONE_NUMBER_ID=${WHATSAPP_PHONE_NUMBER_ID}"
  "WHATSAPP_BUSINESS_ACCOUNT_ID=${WHATSAPP_BUSINESS_ACCOUNT_ID:-}"
  "WHATSAPP_GRAPH_API_VERSION=${WHATSAPP_GRAPH_API_VERSION:-v20.0}"
  "WHATSAPP_GRAPH_BASE_URL=${WHATSAPP_GRAPH_BASE_URL:-https://graph.facebook.com}"
  "ACADEMIC_AGENT_REMINDER_CHANNELS=${ACADEMIC_AGENT_REMINDER_CHANNELS:-whatsapp}"
  "LOG_LEVEL=${LOG_LEVEL:-INFO}"
)

if az containerapp job show \
     --name "$AZ_REMINDER_JOB_NAME" \
     --resource-group "$AZ_RESOURCE_GROUP" \
     >/dev/null 2>&1; then

  info "== Actualizando Container Apps Job: $AZ_REMINDER_JOB_NAME =="

  az containerapp job secret set \
    --name "$AZ_REMINDER_JOB_NAME" \
    --resource-group "$AZ_RESOURCE_GROUP" \
    --secrets "${SECRETS[@]}" \
    >/dev/null

  az containerapp job update \
    --name "$AZ_REMINDER_JOB_NAME" \
    --resource-group "$AZ_RESOURCE_GROUP" \
    --image "$IMAGE_REF" \
    --cron-expression "$CRON_SCHEDULE" \
    --replica-timeout "$REPLICA_TIMEOUT" \
    --set-env-vars "${ENV_VARS[@]}" \
    >/dev/null

else

  info "== Creando Container Apps Job: $AZ_REMINDER_JOB_NAME =="

  az containerapp job create \
    --name "$AZ_REMINDER_JOB_NAME" \
    --resource-group "$AZ_RESOURCE_GROUP" \
    --environment "$AZ_CONTAINERAPPS_ENV" \
    --trigger-type Schedule \
    --cron-expression "$CRON_SCHEDULE" \
    --replica-timeout "$REPLICA_TIMEOUT" \
    --replica-retry-limit 1 \
    --replica-completion-count 1 \
    --parallelism 1 \
    --image "$IMAGE_REF" \
    --registry-server "$AZ_ACR_NAME.azurecr.io" \
    --registry-username "$AZ_ACR_NAME" \
    --registry-password "$ACR_PASSWORD" \
    --command "python" \
    --args "/app/scripts/run_due_whatsapp_reminders.py" \
    --secrets "${SECRETS[@]}" \
    --env-vars "${ENV_VARS[@]}" \
    >/dev/null

fi

info ""
info "Deploy del job terminado."
info "Job:      $AZ_REMINDER_JOB_NAME"
info "Imagen:   $IMAGE_REF"
info "Cron:     $CRON_SCHEDULE  (cada 5 minutos UTC)"
info "Timeout:  ${REPLICA_TIMEOUT}s por ejecución"
info ""
info "Ver historial de ejecuciones:"
info "  az containerapp job execution list --name $AZ_REMINDER_JOB_NAME --resource-group $AZ_RESOURCE_GROUP -o table"
info ""
info "Ver logs de la última ejecución:"
info "  EXEC_ID=\$(az containerapp job execution list --name $AZ_REMINDER_JOB_NAME --resource-group $AZ_RESOURCE_GROUP --query '[0].name' -o tsv)"
info "  az containerapp job execution show --name $AZ_REMINDER_JOB_NAME --resource-group $AZ_RESOURCE_GROUP --job-execution-name \$EXEC_ID"
info ""
info "Disparar manualmente (para probar):"
info "  az containerapp job start --name $AZ_REMINDER_JOB_NAME --resource-group $AZ_RESOURCE_GROUP"
