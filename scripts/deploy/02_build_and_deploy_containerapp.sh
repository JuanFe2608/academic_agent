#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY_ENV="$ROOT_DIR/scripts/deploy/azure-pilot.env"
APP_ENV="$ROOT_DIR/.env"

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

info() {
  printf '%s\n' "$1"
}

[[ -f "$DEPLOY_ENV" ]] || fail "No existe $DEPLOY_ENV"
[[ -f "$APP_ENV" ]] || fail "No existe $APP_ENV"

set -a
# shellcheck source=/dev/null
source "$DEPLOY_ENV"
# shellcheck source=/dev/null
source "$APP_ENV"
set +a

# --- Validaciones críticas antes de desplegar ---
[[ -n "$AZURE_OPENAI_ENDPOINT" ]]              || fail "AZURE_OPENAI_ENDPOINT no está definido"
[[ -n "$AZURE_OPENAI_API_KEY" ]]               || fail "AZURE_OPENAI_API_KEY no está definido"
[[ -n "$AZURE_OPENAI_DEPLOYMENT_NAME" ]]        || fail "AZURE_OPENAI_DEPLOYMENT_NAME no está definido"
[[ -n "$OPENAI_API_VERSION" ]]                  || fail "OPENAI_API_VERSION no está definido"
[[ -n "$AZURE_OPENAI_API_KEY_TRANSCRIBE" ]]     || fail "AZURE_OPENAI_API_KEY_TRANSCRIBE no está definido"
[[ -n "$AZURE_OPENAI_ENDPOINT_TRANSCRIBE" ]]    || fail "AZURE_OPENAI_ENDPOINT_TRANSCRIBE no está definido"
[[ -n "$AZURE_OPENAI_DEPLOYMENT_NAME_TRANSCRIBE" ]] || fail "AZURE_OPENAI_DEPLOYMENT_NAME_TRANSCRIBE no está definido"
[[ -n "$OPENAI_API_VERSION_TRANSCRIBE" ]]       || fail "OPENAI_API_VERSION_TRANSCRIBE no está definido"

# El endpoint debe ser la URL base del recurso, sin path ni query
if [[ "$AZURE_OPENAI_ENDPOINT" == *"/openai"* ]] || [[ "$AZURE_OPENAI_ENDPOINT" == *"?"* ]]; then
  fail "AZURE_OPENAI_ENDPOINT tiene un path o query string. Debe ser solo: https://resource.openai.azure.com"
fi
if [[ "$AZURE_OPENAI_ENDPOINT_TRANSCRIBE" == *"/openai"* ]] || [[ "$AZURE_OPENAI_ENDPOINT_TRANSCRIBE" == *"?"* ]]; then
  fail "AZURE_OPENAI_ENDPOINT_TRANSCRIBE tiene un path o query string. Debe ser solo: https://resource.openai.azure.com"
fi

# El deployment de chat NO puede ser un modelo de transcripción
for blocked in transcribe transcription whisper tts; do
  if [[ "${AZURE_OPENAI_DEPLOYMENT_NAME,,}" == *"$blocked"* ]]; then
    fail "AZURE_OPENAI_DEPLOYMENT_NAME='$AZURE_OPENAI_DEPLOYMENT_NAME' parece ser un modelo de audio. Usa el deployment de chat (ej: gpt-4o-mini)."
  fi
done

command -v az >/dev/null 2>&1 || fail "Azure CLI no esta instalado o no esta en PATH"
az account show >/dev/null 2>&1 || fail "Azure CLI no tiene sesion activa. Ejecuta: az login"

IMAGE_REF="$AZ_ACR_NAME.azurecr.io/$AZ_IMAGE_NAME:$AZ_IMAGE_TAG"

info "== Preparando extensiones Azure CLI =="
az extension add --name containerapp --upgrade >/dev/null

info "== Creando/confirmando recursos base =="
az group create \
  --name "$AZ_RESOURCE_GROUP" \
  --location "$AZ_LOCATION" \
  >/dev/null

az acr show \
  --name "$AZ_ACR_NAME" \
  --resource-group "$AZ_RESOURCE_GROUP" \
  >/dev/null 2>&1 || \
az acr create \
  --name "$AZ_ACR_NAME" \
  --resource-group "$AZ_RESOURCE_GROUP" \
  --sku Basic \
  --admin-enabled true \
  >/dev/null

az containerapp env show \
  --name "$AZ_CONTAINERAPPS_ENV" \
  --resource-group "$AZ_RESOURCE_GROUP" \
  >/dev/null 2>&1 || \
az containerapp env create \
  --name "$AZ_CONTAINERAPPS_ENV" \
  --resource-group "$AZ_RESOURCE_GROUP" \
  --location "$AZ_LOCATION" \
  >/dev/null

info "== Construyendo imagen en ACR: $IMAGE_REF =="
az acr build \
  --registry "$AZ_ACR_NAME" \
  --image "$AZ_IMAGE_NAME:$AZ_IMAGE_TAG" \
  "$ROOT_DIR"

info "== Obteniendo credenciales ACR =="
ACR_PASSWORD="$(az acr credential show --name "$AZ_ACR_NAME" --query 'passwords[0].value' -o tsv)"

info "== Creando o actualizando Container App =="
if az containerapp show --name "$AZ_CONTAINERAPP_NAME" --resource-group "$AZ_RESOURCE_GROUP" >/dev/null 2>&1; then
  az containerapp registry set \
    --name "$AZ_CONTAINERAPP_NAME" \
    --resource-group "$AZ_RESOURCE_GROUP" \
    --server "$AZ_ACR_NAME.azurecr.io" \
    --username "$AZ_ACR_NAME" \
    --password "$ACR_PASSWORD" \
    >/dev/null

  az containerapp secret set \
    --name "$AZ_CONTAINERAPP_NAME" \
    --resource-group "$AZ_RESOURCE_GROUP" \
    --secrets \
      academic-agent-database-url="$ACADEMIC_AGENT_DATABASE_URL" \
      langgraph-checkpointer-database-url="${LANGGRAPH_CHECKPOINTER_DATABASE_URL:-$ACADEMIC_AGENT_DATABASE_URL}" \
      azure-openai-api-key="$AZURE_OPENAI_API_KEY" \
      azure-openai-api-key-transcribe="$AZURE_OPENAI_API_KEY_TRANSCRIBE" \
      whatsapp-access-token="$WHATSAPP_ACCESS_TOKEN" \
      whatsapp-verify-token="$WHATSAPP_VERIFY_TOKEN" \
      whatsapp-app-secret="$WHATSAPP_APP_SECRET" \
      ms-client-secret="$MS_CLIENT_SECRET" \
      reminder-worker-token="$ACADEMIC_AGENT_REMINDER_WORKER_TOKEN" \
    >/dev/null

  az containerapp update \
    --name "$AZ_CONTAINERAPP_NAME" \
    --resource-group "$AZ_RESOURCE_GROUP" \
    --image "$IMAGE_REF" \
    --min-replicas "$AZ_MIN_REPLICAS" \
    --max-replicas "$AZ_MAX_REPLICAS" \
    --set-env-vars \
      ACADEMIC_AGENT_DATABASE_URL=secretref:academic-agent-database-url \
      LANGGRAPH_CHECKPOINTER_DATABASE_URL=secretref:langgraph-checkpointer-database-url \
      AZURE_OPENAI_API_KEY=secretref:azure-openai-api-key \
      AZURE_OPENAI_ENDPOINT="$AZURE_OPENAI_ENDPOINT" \
      AZURE_OPENAI_DEPLOYMENT_NAME="$AZURE_OPENAI_DEPLOYMENT_NAME" \
      AZURE_OPENAI_DEPLOYMENT_NAME_EMBEDDINGS="$AZURE_OPENAI_DEPLOYMENT_NAME_EMBEDDINGS" \
      OPENAI_API_VERSION="$OPENAI_API_VERSION" \
      AZURE_OPENAI_API_KEY_TRANSCRIBE=secretref:azure-openai-api-key-transcribe \
      AZURE_OPENAI_ENDPOINT_TRANSCRIBE="$AZURE_OPENAI_ENDPOINT_TRANSCRIBE" \
      AZURE_OPENAI_DEPLOYMENT_NAME_TRANSCRIBE="$AZURE_OPENAI_DEPLOYMENT_NAME_TRANSCRIBE" \
      OPENAI_API_VERSION_TRANSCRIBE="$OPENAI_API_VERSION_TRANSCRIBE" \
      WHATSAPP_PHONE_NUMBER_ID="$WHATSAPP_PHONE_NUMBER_ID" \
      WHATSAPP_BUSINESS_ACCOUNT_ID="$WHATSAPP_BUSINESS_ACCOUNT_ID" \
      WHATSAPP_ACCESS_TOKEN=secretref:whatsapp-access-token \
      WHATSAPP_VERIFY_TOKEN=secretref:whatsapp-verify-token \
      WHATSAPP_APP_SECRET=secretref:whatsapp-app-secret \
      WHATSAPP_GRAPH_API_VERSION="${WHATSAPP_GRAPH_API_VERSION:-v20.0}" \
      WHATSAPP_GRAPH_BASE_URL="${WHATSAPP_GRAPH_BASE_URL:-https://graph.facebook.com}" \
      MS_CLIENT_ID="$MS_CLIENT_ID" \
      MS_CLIENT_SECRET=secretref:ms-client-secret \
      MS_TENANT_ID="$MS_TENANT_ID" \
      MICROSOFT_REDIRECT_URI="$MICROSOFT_REDIRECT_URI" \
      ACADEMIC_AGENT_PUBLIC_BASE_URL="${ACADEMIC_AGENT_PUBLIC_BASE_URL:-}" \
      LARA_HABEAS_DATA_URL="${LARA_HABEAS_DATA_URL:-}" \
      ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH="${ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH:-1}" \
      ACADEMIC_AGENT_EMAIL_VERIFICATION_MODE="${ACADEMIC_AGENT_EMAIL_VERIFICATION_MODE:-disabled}" \
      ACADEMIC_AGENT_ALLOWED_EMAIL_DOMAINS="${ACADEMIC_AGENT_ALLOWED_EMAIL_DOMAINS:-outlook.com,hotmail.com,live.com,msn.com}" \
      ACADEMIC_AGENT_ENABLE_PERSONALIZATION_MODULE="${ACADEMIC_AGENT_ENABLE_PERSONALIZATION_MODULE:-1}" \
      ACADEMIC_AGENT_ENABLE_PRIORITIES_MODULE="${ACADEMIC_AGENT_ENABLE_PRIORITIES_MODULE:-1}" \
      ACADEMIC_AGENT_ENABLE_POST_RADAR_FLOW="${ACADEMIC_AGENT_ENABLE_POST_RADAR_FLOW:-1}" \
      ACADEMIC_AGENT_ENABLE_STUDY_PLAN_MATERIALIZATION="${ACADEMIC_AGENT_ENABLE_STUDY_PLAN_MATERIALIZATION:-1}" \
      ACADEMIC_AGENT_ENABLE_STUDY_PLAN_REMINDERS="${ACADEMIC_AGENT_ENABLE_STUDY_PLAN_REMINDERS:-1}" \
      ACADEMIC_AGENT_REMINDER_CHANNELS="${ACADEMIC_AGENT_REMINDER_CHANNELS:-whatsapp}" \
      ACADEMIC_AGENT_REMINDER_WORKER_TOKEN=secretref:reminder-worker-token \
      ACADEMIC_AGENT_MEDIA_DIR="${ACADEMIC_AGENT_MEDIA_DIR:-/tmp/academic_agent_media}" \
      ACADEMIC_AGENT_SCHEDULE_DIR="${ACADEMIC_AGENT_SCHEDULE_DIR:-/tmp/academic_agent_schedules}" \
      RAG_ENABLED="${RAG_ENABLED:-true}" \
      LOG_LEVEL="${LOG_LEVEL:-INFO}" \
      MEDIA_INLINE_PREVIEW="${MEDIA_INLINE_PREVIEW:-false}" \
    >/dev/null
else
  az containerapp create \
    --name "$AZ_CONTAINERAPP_NAME" \
    --resource-group "$AZ_RESOURCE_GROUP" \
    --environment "$AZ_CONTAINERAPPS_ENV" \
    --image "$IMAGE_REF" \
    --registry-server "$AZ_ACR_NAME.azurecr.io" \
    --registry-username "$AZ_ACR_NAME" \
    --registry-password "$ACR_PASSWORD" \
    --ingress external \
    --target-port "$AZ_TARGET_PORT" \
    --min-replicas "$AZ_MIN_REPLICAS" \
    --max-replicas "$AZ_MAX_REPLICAS" \
    --secrets \
      academic-agent-database-url="$ACADEMIC_AGENT_DATABASE_URL" \
      langgraph-checkpointer-database-url="${LANGGRAPH_CHECKPOINTER_DATABASE_URL:-$ACADEMIC_AGENT_DATABASE_URL}" \
      azure-openai-api-key="$AZURE_OPENAI_API_KEY" \
      azure-openai-api-key-transcribe="$AZURE_OPENAI_API_KEY_TRANSCRIBE" \
      whatsapp-access-token="$WHATSAPP_ACCESS_TOKEN" \
      whatsapp-verify-token="$WHATSAPP_VERIFY_TOKEN" \
      whatsapp-app-secret="$WHATSAPP_APP_SECRET" \
      ms-client-secret="$MS_CLIENT_SECRET" \
      reminder-worker-token="$ACADEMIC_AGENT_REMINDER_WORKER_TOKEN" \
    --env-vars \
      ACADEMIC_AGENT_DATABASE_URL=secretref:academic-agent-database-url \
      LANGGRAPH_CHECKPOINTER_DATABASE_URL=secretref:langgraph-checkpointer-database-url \
      AZURE_OPENAI_API_KEY=secretref:azure-openai-api-key \
      AZURE_OPENAI_ENDPOINT="$AZURE_OPENAI_ENDPOINT" \
      AZURE_OPENAI_DEPLOYMENT_NAME="$AZURE_OPENAI_DEPLOYMENT_NAME" \
      AZURE_OPENAI_DEPLOYMENT_NAME_EMBEDDINGS="$AZURE_OPENAI_DEPLOYMENT_NAME_EMBEDDINGS" \
      OPENAI_API_VERSION="$OPENAI_API_VERSION" \
      AZURE_OPENAI_API_KEY_TRANSCRIBE=secretref:azure-openai-api-key-transcribe \
      AZURE_OPENAI_ENDPOINT_TRANSCRIBE="$AZURE_OPENAI_ENDPOINT_TRANSCRIBE" \
      AZURE_OPENAI_DEPLOYMENT_NAME_TRANSCRIBE="$AZURE_OPENAI_DEPLOYMENT_NAME_TRANSCRIBE" \
      OPENAI_API_VERSION_TRANSCRIBE="$OPENAI_API_VERSION_TRANSCRIBE" \
      WHATSAPP_PHONE_NUMBER_ID="$WHATSAPP_PHONE_NUMBER_ID" \
      WHATSAPP_BUSINESS_ACCOUNT_ID="$WHATSAPP_BUSINESS_ACCOUNT_ID" \
      WHATSAPP_ACCESS_TOKEN=secretref:whatsapp-access-token \
      WHATSAPP_VERIFY_TOKEN=secretref:whatsapp-verify-token \
      WHATSAPP_APP_SECRET=secretref:whatsapp-app-secret \
      WHATSAPP_GRAPH_API_VERSION="${WHATSAPP_GRAPH_API_VERSION:-v20.0}" \
      WHATSAPP_GRAPH_BASE_URL="${WHATSAPP_GRAPH_BASE_URL:-https://graph.facebook.com}" \
      MS_CLIENT_ID="$MS_CLIENT_ID" \
      MS_CLIENT_SECRET=secretref:ms-client-secret \
      MS_TENANT_ID="$MS_TENANT_ID" \
      MICROSOFT_REDIRECT_URI="$MICROSOFT_REDIRECT_URI" \
      ACADEMIC_AGENT_PUBLIC_BASE_URL="${ACADEMIC_AGENT_PUBLIC_BASE_URL:-}" \
      LARA_HABEAS_DATA_URL="${LARA_HABEAS_DATA_URL:-}" \
      ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH="${ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH:-1}" \
      ACADEMIC_AGENT_EMAIL_VERIFICATION_MODE="${ACADEMIC_AGENT_EMAIL_VERIFICATION_MODE:-disabled}" \
      ACADEMIC_AGENT_ALLOWED_EMAIL_DOMAINS="${ACADEMIC_AGENT_ALLOWED_EMAIL_DOMAINS:-outlook.com,hotmail.com,live.com,msn.com}" \
      ACADEMIC_AGENT_ENABLE_PERSONALIZATION_MODULE="${ACADEMIC_AGENT_ENABLE_PERSONALIZATION_MODULE:-1}" \
      ACADEMIC_AGENT_ENABLE_PRIORITIES_MODULE="${ACADEMIC_AGENT_ENABLE_PRIORITIES_MODULE:-1}" \
      ACADEMIC_AGENT_ENABLE_POST_RADAR_FLOW="${ACADEMIC_AGENT_ENABLE_POST_RADAR_FLOW:-1}" \
      ACADEMIC_AGENT_ENABLE_STUDY_PLAN_MATERIALIZATION="${ACADEMIC_AGENT_ENABLE_STUDY_PLAN_MATERIALIZATION:-1}" \
      ACADEMIC_AGENT_ENABLE_STUDY_PLAN_REMINDERS="${ACADEMIC_AGENT_ENABLE_STUDY_PLAN_REMINDERS:-1}" \
      ACADEMIC_AGENT_REMINDER_CHANNELS="${ACADEMIC_AGENT_REMINDER_CHANNELS:-whatsapp}" \
      ACADEMIC_AGENT_REMINDER_WORKER_TOKEN=secretref:reminder-worker-token \
      ACADEMIC_AGENT_MEDIA_DIR="${ACADEMIC_AGENT_MEDIA_DIR:-/tmp/academic_agent_media}" \
      ACADEMIC_AGENT_SCHEDULE_DIR="${ACADEMIC_AGENT_SCHEDULE_DIR:-/tmp/academic_agent_schedules}" \
      RAG_ENABLED="${RAG_ENABLED:-true}" \
      LOG_LEVEL="${LOG_LEVEL:-INFO}" \
      MEDIA_INLINE_PREVIEW="${MEDIA_INLINE_PREVIEW:-false}" \
    >/dev/null
fi

FQDN="$(az containerapp show --name "$AZ_CONTAINERAPP_NAME" --resource-group "$AZ_RESOURCE_GROUP" --query properties.configuration.ingress.fqdn -o tsv)"

info ""
info "Deploy terminado."
info "Imagen: $IMAGE_REF"
info "URL: https://$FQDN"
info "Health: https://$FQDN/health"
info "OAuth callback esperado: https://$FQDN/oauth/callback"
info "WhatsApp webhook esperado: https://$FQDN/webhook"
