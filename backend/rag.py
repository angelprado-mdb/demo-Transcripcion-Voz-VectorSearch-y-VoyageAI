"""
rag.py - Logica RAG completa: Retrieve → Augment → Generate

Flujo:
  1. RETRIEVE: MongoDB $vectorSearch con Auto-Embedding (VoyageAI voyage-4)
               recupera las K llamadas mas semanticamente relevantes
  2. AUGMENT:  Construye el prompt con las transcripciones como contexto
  3. GENERATE: Envia el prompt al LLM elegido por el usuario (OpenAI / Anthropic / Gemini)
               y retorna la respuesta junto con metadata educativa
"""

import json
from typing import Literal
from database import busqueda_vectorial, pipeline_vectorial_str

# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------

LLMProvider = Literal["openai", "anthropic", "gemini", "huggingface"]

MODELOS_DISPONIBLES = {
    "openai": [
        {"id": "gpt-4o", "nombre": "GPT-4o", "descripcion": "Mejor razonamiento"},
        {"id": "gpt-4o-mini", "nombre": "GPT-4o Mini", "descripcion": "Rapido y economico"},
    ],
    "anthropic": [
        {"id": "claude-3-5-sonnet-20241022", "nombre": "Claude 3.5 Sonnet", "descripcion": "Mejor en analisis de texto"},
        {"id": "claude-3-5-haiku-20241022", "nombre": "Claude 3.5 Haiku", "descripcion": "Rapido y economico"},
    ],
    "gemini": [
        {"id": "gemini-2.0-flash", "nombre": "Gemini 2.0 Flash", "descripcion": "Mas reciente, rapido y economico"},
        {"id": "gemini-2.5-flash-preview-05-20", "nombre": "Gemini 2.5 Flash Preview", "descripcion": "Ultimo modelo, razonamiento avanzado"},
        {"id": "gemini-1.5-pro-002", "nombre": "Gemini 1.5 Pro", "descripcion": "Alta capacidad, contexto largo"},
    ],
    "huggingface": [
        {"id": "meta-llama/Llama-3.1-8B-Instruct", "nombre": "Llama 3.1 8B Instruct", "descripcion": "Open source, rapido y eficiente"},
        {"id": "meta-llama/Llama-3.1-70B-Instruct", "nombre": "Llama 3.1 70B Instruct", "descripcion": "Alta capacidad, open source"},
        {"id": "mistralai/Mistral-7B-Instruct-v0.3", "nombre": "Mistral 7B Instruct", "descripcion": "Eficiente y de codigo abierto"},
        {"id": "Qwen/Qwen2.5-72B-Instruct", "nombre": "Qwen 2.5 72B Instruct", "descripcion": "Multilingue, alta capacidad"},
    ],
}


# ---------------------------------------------------------------------------
# PASO 1: RETRIEVE
# ---------------------------------------------------------------------------

def retrieve(pregunta: str, k: int = 5) -> tuple[list, str]:
    """
    Recupera las K llamadas mas relevantes usando MongoDB Vector Search.
    Auto-Embedding vectoriza la pregunta internamente - no se requiere API Key.

    Returns:
        (llamadas, pipeline_str): lista de docs recuperados y el pipeline como texto
    """
    llamadas = busqueda_vectorial(pregunta, k=k, num_candidates=max(k * 10, 50))
    pipeline_str = pipeline_vectorial_str(pregunta, k=k, num_candidates=max(k * 10, 50))
    return llamadas, pipeline_str


# ---------------------------------------------------------------------------
# PASO 2: AUGMENT - Construir el contexto y el prompt
# ---------------------------------------------------------------------------

def _transcripcion_a_texto(transcripcion) -> str:
    """Convierte el array de transcripcion a texto plano legible."""
    if not transcripcion:
        return "(sin transcripcion)"
    if isinstance(transcripcion, str):
        return transcripcion

    lineas = []
    for turno in transcripcion:
        if isinstance(turno, dict):
            hablante = turno.get("hablante", turno.get("rol", "?"))
            texto = turno.get("texto", "")
            tiempo = turno.get("tiempo_marca", "")
            if tiempo:
                lineas.append(f"[{tiempo}] {hablante}: {texto}")
            else:
                lineas.append(f"{hablante}: {texto}")
        else:
            lineas.append(str(turno))
    return "\n".join(lineas)


def augment(pregunta: str, llamadas: list) -> tuple[str, str]:
    """
    Construye el prompt completo para el LLM con las llamadas como contexto.

    Returns:
        (system_prompt, user_prompt): los dos mensajes que se envian al LLM
    """
    system_prompt = """Eres un asistente especializado en analisis de llamadas comerciales.

Se te proporcionan transcripciones de llamadas reales recuperadas de una base de datos \
usando MongoDB Vector Search con Auto-Embedding de VoyageAI (modelo voyage-4). \
Las llamadas estan ordenadas por relevancia semantica a la pregunta del usuario.

Instrucciones:
- Responde UNICAMENTE basandote en la informacion de las llamadas proporcionadas.
- Si la informacion no es suficiente para responder, indicalo claramente.
- Sé conciso pero completo. Usa listas cuando sea util.
- Puedes hacer referencias directas a llamadas especificas (por su ID o cliente).
- Responde siempre en espanol."""

    # Construir el contexto con las llamadas recuperadas
    contexto_partes = []
    for i, llamada in enumerate(llamadas, 1):
        score = llamada.get("score", 0)
        id_llamada = llamada.get("id_llamada", llamada.get("_id", f"Llamada {i}"))
        resultado = llamada.get("resultado_llamada", "N/A")
        agente = llamada.get("agente", {})
        nombre_agente = agente.get("nombre", "N/A") if isinstance(agente, dict) else str(agente)
        cliente = llamada.get("cliente", {})
        nombre_cliente = cliente.get("nombre", "N/A") if isinstance(cliente, dict) else str(cliente)
        duracion = llamada.get("duracion_segundos", "N/A")
        fecha = llamada.get("fecha", "N/A")

        transcripcion_texto = _transcripcion_a_texto(llamada.get("transcripcion", []))

        bloque = f"""--- LLAMADA {i} (Relevancia: {score:.2%}) ---
ID: {id_llamada}
Fecha: {fecha} | Duracion: {duracion}s
Agente: {nombre_agente}
Cliente: {nombre_cliente}
Resultado: {resultado}

TRANSCRIPCION:
{transcripcion_texto}
"""
        contexto_partes.append(bloque)

    contexto = "\n".join(contexto_partes)

    user_prompt = f"""LLAMADAS RECUPERADAS ({len(llamadas)} resultado{"s" if len(llamadas) != 1 else ""} mas relevantes):

{contexto}

---
PREGUNTA: {pregunta}"""

    return system_prompt, user_prompt


# ---------------------------------------------------------------------------
# PASO 3: GENERATE - Llamar al LLM elegido
# ---------------------------------------------------------------------------

async def generate_openai(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    model: str,
    historial: list,
) -> str:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key)

    messages = [{"role": "system", "content": system_prompt}]
    for msg in historial:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_prompt})

    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.3,
        max_tokens=2048,
    )
    return response.choices[0].message.content


async def generate_anthropic(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    model: str,
    historial: list,
) -> str:
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=api_key)

    messages = []
    for msg in historial:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_prompt})

    response = await client.messages.create(
        model=model,
        system=system_prompt,
        messages=messages,
        max_tokens=2048,
        temperature=0.3,
    )
    return response.content[0].text


async def generate_gemini(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    model: str,
    historial: list,
) -> str:
    # Usa el nuevo SDK google-genai (>= 1.0), reemplaza el deprecado google-generativeai
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    # Construir historial en formato del nuevo SDK
    contents = []
    for msg in historial:
        role = "user" if msg["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

    # Agregar el mensaje actual del usuario
    contents.append(types.Content(role="user", parts=[types.Part(text=user_prompt)]))

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.3,
        max_output_tokens=2048,
    )

    response = await client.aio.models.generate_content(
        model=model,
        contents=contents,
        config=config,
    )
    return response.text


async def generate_huggingface(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    model: str,
    historial: list,
    endpoint_url: str = "",
) -> str:
    # Usa el SDK de OpenAI apuntado a la API compatible de Hugging Face.
    # Si se provee endpoint_url se usa como base (p.ej. un Inference Endpoint dedicado);
    # si no, se usa el endpoint serverless publico de HF.
    from openai import AsyncOpenAI

    base_url = endpoint_url.rstrip("/") if endpoint_url else "https://api-inference.huggingface.co/v1"

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    messages = [{"role": "system", "content": system_prompt}]
    for msg in historial:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_prompt})

    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.3,
        max_tokens=2048,
    )
    return response.choices[0].message.content


# ---------------------------------------------------------------------------
# Orquestador RAG principal
# ---------------------------------------------------------------------------

async def rag_chat(
    pregunta: str,
    k: int,
    llm_provider: LLMProvider,
    llm_api_key: str,
    llm_model: str,
    historial: list,
    llm_endpoint_url: str = "",
) -> dict:
    """
    Orquesta el flujo RAG completo y retorna la respuesta junto con
    toda la metadata educativa (pipeline, llamadas recuperadas, prompt).

    Returns dict con:
        - respuesta: texto generado por el LLM
        - llamadas_recuperadas: lista de docs con scores
        - pipeline_ejecutado: string del pipeline $vectorSearch
        - system_prompt: prompt de sistema enviado al LLM
        - user_prompt: prompt de usuario con contexto de llamadas
        - paso_retrieve: metadata del retrieve
        - paso_augment: metadata del augment
        - paso_generate: metadata del generate
    """

    # --- PASO 1: RETRIEVE ---
    llamadas, pipeline_str = retrieve(pregunta, k=k)

    # --- PASO 2: AUGMENT ---
    system_prompt, user_prompt = augment(pregunta, llamadas)

    # --- PASO 3: GENERATE ---
    if not llm_api_key or not llm_api_key.strip():
        raise ValueError("Se requiere una API Key del proveedor LLM para generar la respuesta.")

    generators = {
        "openai": generate_openai,
        "anthropic": generate_anthropic,
        "gemini": generate_gemini,
    }

    if llm_provider == "huggingface":
        respuesta = await generate_huggingface(
            system_prompt, user_prompt, llm_api_key, llm_model, historial,
            endpoint_url=llm_endpoint_url,
        )
    else:
        generator = generators.get(llm_provider)
        if not generator:
            raise ValueError(f"Proveedor LLM no soportado: {llm_provider}. Usa: openai, anthropic, gemini, huggingface")
        respuesta = await generator(system_prompt, user_prompt, llm_api_key, llm_model, historial)

    # Preparar llamadas para la respuesta (sin el vector completo)
    llamadas_resumen = []
    for ll in llamadas:
        ll_copy = {k: v for k, v in ll.items() if k != "transcripcion"}
        ll_copy["transcripcion_preview"] = _transcripcion_preview(ll.get("transcripcion", []))
        llamadas_resumen.append(ll_copy)

    return {
        "respuesta": respuesta,
        "llamadas_recuperadas": llamadas_resumen,
        "llamadas_con_transcripcion": llamadas,
        "pipeline_ejecutado": pipeline_str,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "paso_retrieve": {
            "descripcion": "MongoDB $vectorSearch con Auto-Embedding VoyageAI voyage-4",
            "query": pregunta,
            "k": k,
            "resultados": len(llamadas),
            "nota": "Atlas vectorizo la pregunta internamente. No se requirio API Key para este paso.",
        },
        "paso_augment": {
            "descripcion": "Construccion del contexto con transcripciones recuperadas",
            "llamadas_incluidas": len(llamadas),
            "longitud_prompt": len(user_prompt),
        },
        "paso_generate": {
            "descripcion": "Generacion de respuesta con LLM",
            "proveedor": llm_provider,
            "modelo": llm_model,
            "historial_mensajes": len(historial),
        },
    }


def _transcripcion_preview(transcripcion, max_chars: int = 200) -> str:
    """Primeras palabras de la transcripcion para preview en cards."""
    texto = _transcripcion_a_texto(transcripcion)
    if len(texto) <= max_chars:
        return texto
    return texto[:max_chars].rsplit(" ", 1)[0] + "..."


def get_modelos_disponibles() -> dict:
    return MODELOS_DISPONIBLES
