"""
main.py - FastAPI: API REST para la demo de Vector Search sobre Llamadas

Endpoints:
  GET  /health                        - Estado de la conexion
  GET  /api/modelos                   - Modelos LLM disponibles
  POST /api/llamadas/upload           - Sube JSON de llamada(s)
  GET  /api/llamadas/                 - Lista todas las llamadas
  GET  /api/llamadas/{id}             - Obtiene una llamada por ID
  DELETE /api/llamadas/{id}           - Elimina una llamada
  POST /api/llamadas/search           - Busqueda semantica simple
  GET  /api/llamadas/{id}/embedding   - Vector del embedding de una llamada
  POST /api/llamadas/similitud        - Similitud coseno entre dos llamadas
  GET  /api/embeddings/estado         - Estado de los embeddings generados
  POST /api/chat                      - RAG completo: retrieve + augment + generate
"""

import json
from contextlib import asynccontextmanager
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os

import database
import rag as rag_module


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: verificar conexion
    check = database.health_check()
    if check["status"] == "ok":
        print(f"[OK] Conectado a MongoDB - {check['documentos']} documentos en {check['coleccion']}")
    else:
        print(f"[ERROR] Conexion MongoDB: {check.get('detalle')}")
    yield
    # Shutdown
    if database._client:
        database._client.close()


app = FastAPI(
    title="Voice Demo - MongoDB Vector Search",
    description="Demo educativo de Vector Search y RAG sobre llamadas comerciales",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directorio del frontend (resolvemos la ruta absoluta)
FRONTEND_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "frontend"))


# ---------------------------------------------------------------------------
# Modelos Pydantic
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    query: str
    k: int = 5
    num_candidates: int = 100


class ChatRequest(BaseModel):
    pregunta: str
    k: int = 5
    llm_provider: str = "openai"
    llm_api_key: str
    llm_model: str = "gpt-4o-mini"
    historial: List[dict] = []
    llm_endpoint_url: str = ""


class SimilitudRequest(BaseModel):
    id1: str
    id2: str


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    """Sirve el frontend."""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"mensaje": "Voice Demo API - Vector Search sobre Llamadas", "docs": "/docs"}


@app.get("/style.css")
async def serve_css():
    return FileResponse(os.path.join(FRONTEND_DIR, "style.css"), media_type="text/css")


@app.get("/app.js")
async def serve_js():
    return FileResponse(os.path.join(FRONTEND_DIR, "app.js"), media_type="application/javascript")


@app.get("/health")
async def health():
    """Estado de la conexion a MongoDB."""
    result = database.health_check()
    embeddings = database.contar_embeddings_generados()
    return {
        **result,
        "embeddings": embeddings,
        "indice": database.VECTOR_INDEX_NAME,
        "campo_vectorial": database.VECTOR_FIELD,
    }


@app.get("/api/modelos")
async def get_modelos():
    """Retorna los modelos LLM disponibles por proveedor."""
    return rag_module.get_modelos_disponibles()


# ---------------------------------------------------------------------------
# Llamadas - CRUD
# ---------------------------------------------------------------------------

@app.post("/api/llamadas/upload")
async def upload_llamadas(request: Request):
    """
    Sube una o varias llamadas desde un archivo JSON.
    Acepta tanto un objeto JSON como un array.
    Atlas Auto-Embedding genera los vectores automaticamente al insertar.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON invalido. Verifica el formato del archivo.")

    if not body:
        raise HTTPException(status_code=400, detail="El cuerpo esta vacio.")

    if isinstance(body, list) and len(body) == 0:
        raise HTTPException(status_code=400, detail="El array esta vacio.")

    try:
        result = database.insertar_llamadas(body)
        return {
            **result,
            "mensaje": "Llamada(s) insertada(s) correctamente. Atlas generara los embeddings automaticamente.",
            "nota_auto_embedding": (
                "MongoDB Atlas detecta la insercion via Change Streams y envia el campo "
                f"'{database.VECTOR_FIELD}' a VoyageAI voyage-4 para generar el embedding. "
                "El vector se almacena en __mdb_internal_search, separado de tus documentos."
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al insertar: {str(e)}")


@app.get("/api/llamadas/")
async def listar_llamadas(limite: int = 50, skip: int = 0):
    """Lista todas las llamadas (sin el campo transcripcion completo para eficiencia)."""
    try:
        docs = database.listar_llamadas(limite=limite, skip=skip)
        total = database.get_collection().count_documents({})
        return {"total": total, "retornados": len(docs), "llamadas": docs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/llamadas/{id}")
async def obtener_llamada(id: str):
    """Obtiene una llamada completa por su _id."""
    doc = database.obtener_llamada(id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Llamada con id '{id}' no encontrada.")
    return doc


@app.delete("/api/llamadas/{id}")
async def eliminar_llamada(id: str):
    """
    Elimina una llamada. Atlas elimina automaticamente el embedding
    correspondiente de __mdb_internal_search via Change Streams.
    """
    eliminado = database.eliminar_llamada(id)
    if not eliminado:
        raise HTTPException(status_code=404, detail=f"Llamada con id '{id}' no encontrada.")
    return {
        "eliminado": True,
        "id": id,
        "nota": "Atlas eliminara automaticamente el embedding de __mdb_internal_search.",
    }


# ---------------------------------------------------------------------------
# Busqueda Semantica (simple, sin RAG)
# ---------------------------------------------------------------------------

@app.post("/api/llamadas/search")
async def buscar_llamadas(req: SearchRequest):
    """
    Busqueda semantica usando $vectorSearch con Auto-Embedding.
    No requiere API Key: Atlas vectoriza la query internamente con VoyageAI voyage-4.
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="La query no puede estar vacia.")

    try:
        resultados = database.busqueda_vectorial(req.query, k=req.k, num_candidates=req.num_candidates)
        pipeline_str = database.pipeline_vectorial_str(req.query, k=req.k, num_candidates=req.num_candidates)

        return {
            "query": req.query,
            "resultados": resultados,
            "total_encontrados": len(resultados),
            "pipeline_ejecutado": pipeline_str,
            "nota_auto_embedding": (
                "La query fue vectorizada automaticamente por Atlas usando VoyageAI voyage-4. "
                "No fue necesaria ninguna API Key adicional."
            ),
            "indice": database.VECTOR_INDEX_NAME,
            "campo": database.VECTOR_FIELD,
        }
    except Exception as e:
        error_str = str(e)
        if "index not found" in error_str.lower() or "vectorSearch" in error_str:
            raise HTTPException(
                status_code=503,
                detail=f"Error en Vector Search: {error_str}. Verifica que el indice '{database.VECTOR_INDEX_NAME}' existe y esta READY."
            )
        raise HTTPException(status_code=500, detail=error_str)


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

@app.get("/api/llamadas/{id}/embedding")
async def obtener_embedding(id: str):
    """
    Obtiene el embedding vectorial de una llamada desde __mdb_internal_search.

    El embedding NO esta en el documento original - Atlas lo almacena
    en una base de datos interna separada, gestionada completamente por Atlas.
    """
    result = database.obtener_embedding(id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/api/llamadas/similitud")
async def calcular_similitud(req: SimilitudRequest):
    """
    Calcula la similitud coseno entre los embeddings de dos llamadas.
    Util para demostrar como MongoDB compara vectores en el espacio semantico.
    """
    result = database.calcular_similitud_coseno(req.id1, req.id2)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/api/embeddings/estado")
async def estado_embeddings():
    """
    Cuenta los embeddings generados en __mdb_internal_search.
    Equivalente al comando mongosh de verificacion de la documentacion oficial.
    """
    result = database.contar_embeddings_generados()
    docs_total = database.get_collection().count_documents({})
    result["documentos_en_coleccion"] = docs_total
    result["sincronizacion"] = (
        "Completa" if result.get("total_embeddings", 0) >= docs_total and docs_total > 0
        else "En progreso o pendiente"
    )
    result["comando_verificacion"] = (
        "mongosh \"<connection-string>\" --eval '"
        "print(\"Embeddings: \" + "
        "db.getSiblingDB(\"__mdb_internal_search\")"
        ".getCollectionNames()"
        ".filter(c => /^[0-9a-f]{24}-[0-9a-f]{32}-\\d+-\\d+$/.test(c))"
        ".map(c => db.getSiblingDB(\"__mdb_internal_search\").getCollection(c).countDocuments())"
        ".reduce((a, b) => a + b, 0)); '"
    )
    return result


# ---------------------------------------------------------------------------
# RAG Chat
# ---------------------------------------------------------------------------

@app.post("/api/chat")
async def chat_rag(req: ChatRequest):
    """
    Chat RAG completo sobre las llamadas.

    Flujo:
      1. RETRIEVE: $vectorSearch recupera las K llamadas mas relevantes
                   (Auto-Embedding VoyageAI - sin API Key requerida)
      2. AUGMENT:  Construye el prompt con las transcripciones como contexto
      3. GENERATE: Envia al LLM elegido (OpenAI / Anthropic / Gemini)

    Retorna la respuesta + toda la metadata educativa del proceso RAG.
    """
    if not req.pregunta.strip():
        raise HTTPException(status_code=400, detail="La pregunta no puede estar vacia.")

    if not req.llm_api_key or not req.llm_api_key.strip():
        raise HTTPException(
            status_code=400,
            detail="Se requiere una API Key del proveedor LLM. La API Key nunca se almacena en el servidor."
        )

    if req.llm_provider not in ["openai", "anthropic", "gemini", "huggingface"]:
        raise HTTPException(
            status_code=400,
            detail=f"Proveedor '{req.llm_provider}' no soportado. Usa: openai, anthropic, gemini, huggingface"
        )

    if req.k < 1 or req.k > 20:
        raise HTTPException(status_code=400, detail="k debe estar entre 1 y 20.")

    try:
        result = await rag_module.rag_chat(
            pregunta=req.pregunta,
            k=req.k,
            llm_provider=req.llm_provider,
            llm_api_key=req.llm_api_key,
            llm_model=req.llm_model,
            historial=req.historial,
            llm_endpoint_url=req.llm_endpoint_url,
        )
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        error_str = str(e)
        # Errores comunes de API keys invalidas
        if any(x in error_str.lower() for x in ["api key", "unauthorized", "authentication", "invalid_api_key", "403"]):
            raise HTTPException(
                status_code=401,
                detail=f"API Key invalida o sin permisos: {error_str}"
            )
        raise HTTPException(status_code=500, detail=f"Error en el proceso RAG: {error_str}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    # Sin --reload para evitar el loop con google-generativeai
    # Usa start.sh que pasa --reload-dir apuntando solo al codigo fuente
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
