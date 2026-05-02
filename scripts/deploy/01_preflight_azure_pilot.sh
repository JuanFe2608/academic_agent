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

require_file() {
  [[ -f "$1" ]] || fail "No existe $1"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "No esta instalado o no esta en PATH: $1"
}

require_var() {
  local name="$1"
  local value="${!name:-}"
  [[ -n "$value" ]] || fail "Variable requerida sin valor: $name"
  info "$name=SET"
}

validate_azure_endpoint_base() {
  local name="$1"
  local value="${!name:-}"
  case "$value" in
    http://*|https://*)
      ;;
    *)
      fail "$name debe ser una URL absoluta del recurso Azure OpenAI"
      ;;
  esac
  case "$value" in
    *"/openai/"*|*"/deployments/"*|*"/audio/"*|*"?api-version="*)
      fail "$name debe ser el endpoint base, por ejemplo https://<recurso>.cognitiveservices.azure.com"
      ;;
  esac
  info "$name=BASE_ENDPOINT_OK"
}

validate_chat_deployment() {
  local name="$1"
  local value="${!name:-}"
  local normalized="${value,,}"
  case "$normalized" in
    *audio*|*transcribe*|*transcription*|*tts*|*whisper*)
      fail "$name parece ser un deployment de audio; usa aqui el deployment de chat/vision"
      ;;
  esac
  info "$name=CHAT_DEPLOYMENT_OK"
}

validate_transcription_deployment() {
  local name="$1"
  local value="${!name:-}"
  local normalized="${value,,}"
  case "$normalized" in
    *transcribe*|*transcription*|*whisper*)
      info "$name=TRANSCRIPTION_DEPLOYMENT_OK"
      ;;
    *)
      fail "$name debe apuntar a un deployment de transcripcion de audio"
      ;;
  esac
}

require_file "$DEPLOY_ENV"
require_file "$APP_ENV"

set -a
# shellcheck source=/dev/null
source "$DEPLOY_ENV"
# shellcheck source=/dev/null
source "$APP_ENV"
set +a

info "== Herramientas =="
require_cmd az
az account show >/dev/null 2>&1 || fail "Azure CLI no tiene sesion activa. Ejecuta: az login"
info "az=OK"

info ""
info "== Configuracion Azure =="
for var in \
  AZ_RESOURCE_GROUP \
  AZ_LOCATION \
  AZ_ACR_NAME \
  AZ_CONTAINERAPPS_ENV \
  AZ_CONTAINERAPP_NAME \
  AZ_IMAGE_NAME \
  AZ_IMAGE_TAG \
  AZ_TARGET_PORT \
  AZ_MIN_REPLICAS \
  AZ_MAX_REPLICAS
do
  require_var "$var"
done

info ""
info "== Secretos/aplicacion =="
for var in \
  ACADEMIC_AGENT_DATABASE_URL \
  AZURE_OPENAI_API_KEY \
  AZURE_OPENAI_ENDPOINT \
  AZURE_OPENAI_DEPLOYMENT_NAME \
  AZURE_OPENAI_DEPLOYMENT_NAME_EMBEDDINGS \
  OPENAI_API_VERSION \
  AZURE_OPENAI_API_KEY_TRANSCRIBE \
  AZURE_OPENAI_ENDPOINT_TRANSCRIBE \
  AZURE_OPENAI_DEPLOYMENT_NAME_TRANSCRIBE \
  OPENAI_API_VERSION_TRANSCRIBE \
  WHATSAPP_PHONE_NUMBER_ID \
  WHATSAPP_BUSINESS_ACCOUNT_ID \
  WHATSAPP_ACCESS_TOKEN \
  WHATSAPP_VERIFY_TOKEN \
  WHATSAPP_APP_SECRET \
  MS_CLIENT_ID \
  MS_CLIENT_SECRET \
  MS_TENANT_ID \
  MICROSOFT_REDIRECT_URI \
  ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH \
  ACADEMIC_AGENT_REMINDER_WORKER_TOKEN
do
  require_var "$var"
done

validate_azure_endpoint_base AZURE_OPENAI_ENDPOINT
validate_chat_deployment AZURE_OPENAI_DEPLOYMENT_NAME
validate_azure_endpoint_base AZURE_OPENAI_ENDPOINT_TRANSCRIBE
validate_transcription_deployment AZURE_OPENAI_DEPLOYMENT_NAME_TRANSCRIBE

case "${ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH,,}" in
  1|true|yes|on|required|obligatorio)
    info "ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH=ENABLED"
    ;;
  *)
    fail "ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH debe estar activo para el piloto OAuth"
    ;;
esac

case "${ACADEMIC_AGENT_EMAIL_VERIFICATION_MODE:-disabled}" in
  disabled|fixed|strict)
    info "ACADEMIC_AGENT_EMAIL_VERIFICATION_MODE=${ACADEMIC_AGENT_EMAIL_VERIFICATION_MODE:-disabled}"
    ;;
  *)
    fail "ACADEMIC_AGENT_EMAIL_VERIFICATION_MODE debe ser disabled, fixed o strict"
    ;;
esac

case "$MICROSOFT_REDIRECT_URI" in
  *localhost*|*127.0.0.1*|*TU_DOMINIO*)
    if [[ "${AZ_ALLOW_PLACEHOLDER_REDIRECT_FOR_FIRST_DEPLOY:-false}" == "true" ]]; then
      info "MICROSOFT_REDIRECT_URI=PLACEHOLDER_ALLOWED_FOR_FIRST_DEPLOY"
      info "ADVERTENCIA: despues del primer deploy debes actualizar MICROSOFT_REDIRECT_URI con el FQDN real y redeployar."
    else
      fail "MICROSOFT_REDIRECT_URI aun no apunta al dominio publico de Azure"
    fi
    ;;
  https://*/oauth/callback)
    info "MICROSOFT_REDIRECT_URI=LOOKS_READY"
    ;;
  *)
    fail "MICROSOFT_REDIRECT_URI debe verse como https://<dominio>/oauth/callback"
    ;;
esac

info ""
info "Preflight OK. Ya se puede construir/desplegar la revision piloto."
