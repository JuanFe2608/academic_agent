# Integración WhatsApp

Esta carpeta contiene solo adaptadores de proveedor para WhatsApp Cloud API.

- La lógica de negocio que use WhatsApp vive en `services/channels/`.
- Los nodos de `agents/` no deben llamar este paquete directamente.
- Los archivos multimedia no se guardan como base64 en el estado del grafo.

## Variables de entorno

- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`
- `WHATSAPP_GRAPH_API_VERSION` opcional, por defecto `v20.0`
- `WHATSAPP_GRAPH_BASE_URL` opcional, por defecto `https://graph.facebook.com`
- `ACADEMIC_AGENT_MEDIA_DIR` opcional, por defecto `.langgraph_media`

## Flujo de media

Entrada:

1. El webhook entrega un `media.id`.
2. `WhatsAppCloudClient.download_media()` descarga el archivo a `ACADEMIC_AGENT_MEDIA_DIR`.
3. `WhatsAppChannelService.download_inbound()` devuelve un `ChannelInboundMessage`.
4. `whatsapp_inbound_to_human_message()` crea un `HumanMessage` con ruta local liviana.

Salida:

1. El agente produce texto y/o `image_url` con ruta local.
2. `WhatsAppChannelService` transforma el mensaje en `ChannelOutboundMessage`.
3. Si la imagen es local, se sube con `/media` y luego se envia por `/messages`.
4. Si la imagen es una URL publica, se envia como `link`.
