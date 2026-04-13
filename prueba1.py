

from dotenv import load_dotenv
import os
from openai import AzureOpenAI

# Cargar variables de entorno
load_dotenv()

# Validar variables necesarias
required_vars = [
    "AZURE_OPENAI_API_KEY",
    "OPENAI_API_VERSION",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT_NAME"
]

for var in required_vars:
    if not os.getenv(var):
        raise ValueError(f"Falta la variable de entorno: {var}")

# Crear cliente
client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
)

deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

# Hacer la solicitud
response = client.chat.completions.create(
    model=deployment_name,
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "I am going to Paris, what should I see?"}
    ],
    max_tokens=800,
    temperature=0.7
)

# Imprimir respuesta
print(response.choices[0].message.content)