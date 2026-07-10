"""
database.py - Conexion MongoDB y operaciones sobre la coleccion Llamadas
y la base de datos interna __mdb_internal_search (Auto-Embedding de Atlas)
"""

import os
import json
import struct
from typing import Optional
from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "")
DB_NAME = os.getenv("DB_NAME", "Llamadas")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "Llamadas")
VECTOR_INDEX_NAME = os.getenv("VECTOR_INDEX_NAME", "vector_index")
VECTOR_FIELD = os.getenv("VECTOR_FIELD", "transcripcion_texto")
MDB_INTERNAL_DB = "__mdb_internal_search"

_client: Optional[MongoClient] = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(MONGODB_URI)
    return _client


def get_collection():
    return get_client()[DB_NAME][COLLECTION_NAME]


def health_check() -> dict:
    try:
        client = get_client()
        client.admin.command("ping")
        col = get_collection()
        count = col.count_documents({})
        return {"status": "ok", "documentos": count, "coleccion": f"{DB_NAME}.{COLLECTION_NAME}"}
    except ConnectionFailure as e:
        return {"status": "error", "detalle": str(e)}


# ---------------------------------------------------------------------------
# Insertar llamadas (una o varias)
# ---------------------------------------------------------------------------

def _serialize_doc(doc: dict) -> dict:
    """Convierte _id ObjectId a string para respuestas JSON."""
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


def _transcripcion_a_texto(trans) -> str:
    """
    Convierte el array de transcripcion a texto plano para vectorizacion.
    Atlas Auto-Embedding requiere un campo string, no un array de objetos.
    """
    if not trans:
        return ""
    if isinstance(trans, str):
        return trans
    if isinstance(trans, list):
        lineas = []
        for t in trans:
            if isinstance(t, dict):
                hablante = t.get("hablante", t.get("rol", ""))
                texto = t.get("texto", "")
                if texto:
                    lineas.append(f"{hablante}: {texto}")
            else:
                lineas.append(str(t))
        return "\n".join(lineas)
    return str(trans)


def _preparar_doc(doc: dict) -> dict:
    """
    Agrega el campo transcripcion_texto antes de insertar.
    Este campo de texto plano es el que usa Auto-Embedding para vectorizar.
    El campo transcripcion original (array) se conserva intacto para mostrar en la UI.
    """
    trans = doc.get("transcripcion")
    if trans is not None and "transcripcion_texto" not in doc:
        doc["transcripcion_texto"] = _transcripcion_a_texto(trans)
    return doc


def insertar_llamadas(data) -> dict:
    col = get_collection()
    if isinstance(data, list):
        docs = [_preparar_doc(d) for d in data]
        result = col.insert_many(docs)
        ids = [str(i) for i in result.inserted_ids]
        return {"insertados": len(ids), "ids": ids}
    else:
        doc = _preparar_doc(data)
        result = col.insert_one(doc)
        return {"insertados": 1, "ids": [str(result.inserted_id)]}


# ---------------------------------------------------------------------------
# Listar llamadas
# ---------------------------------------------------------------------------

def listar_llamadas(limite: int = 50, skip: int = 0) -> list:
    col = get_collection()
    # Excluimos transcripcion y transcripcion_texto del listado para eficiencia
    docs = list(col.find({}, {"transcripcion": 0, "transcripcion_texto": 0}).skip(skip).limit(limite))
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


def obtener_llamada(id: str) -> Optional[dict]:
    col = get_collection()
    try:
        doc = col.find_one({"_id": ObjectId(id)})
    except Exception:
        doc = col.find_one({"_id": id})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


# ---------------------------------------------------------------------------
# Eliminar llamada
# ---------------------------------------------------------------------------

def eliminar_llamada(id: str) -> bool:
    col = get_collection()
    try:
        result = col.delete_one({"_id": ObjectId(id)})
    except Exception:
        result = col.delete_one({"_id": id})
    return result.deleted_count > 0


# ---------------------------------------------------------------------------
# Vector Search
# ---------------------------------------------------------------------------

def busqueda_vectorial(query: str, k: int = 5, num_candidates: int = 100) -> list:
    """
    Busqueda semantica usando $vectorSearch con Auto-Embedding.
    Atlas vectoriza la query internamente usando el modelo configurado (voyage-4).
    NO se requiere API Key para esta operacion.
    """
    col = get_collection()

    pipeline = [
        {
            "$vectorSearch": {
                "index": VECTOR_INDEX_NAME,
                "path": VECTOR_FIELD,
                "query": query,
                "numCandidates": num_candidates,
                "limit": k,
            }
        },
        {
            "$project": {
                "score": {"$meta": "vectorSearchScore"},
                "id_llamada": 1,
                "fecha": 1,
                "hora_inicio": 1,
                "duracion_segundos": 1,
                "empresa": 1,
                "agente": 1,
                "cliente": 1,
                "producto": 1,
                "resultado_llamada": 1,
                "transcripcion": 1,
            }
        },
    ]

    results = list(col.aggregate(pipeline))
    for r in results:
        r["_id"] = str(r["_id"])
    return results


def pipeline_vectorial_str(query: str, k: int = 5, num_candidates: int = 100) -> str:
    """
    Retorna el pipeline como codigo Python completo con imports y driver syntax,
    listo para copiar y ejecutar.
    """
    pipeline_json = json.dumps(
        [
            {
                "$vectorSearch": {
                    "index": VECTOR_INDEX_NAME,
                    "path": VECTOR_FIELD,
                    "query": query,
                    "numCandidates": num_candidates,
                    "limit": k,
                }
            },
            {
                "$project": {
                    "score": {"$meta": "vectorSearchScore"},
                    "id_llamada": 1,
                    "agente": 1,
                    "cliente": 1,
                    "resultado_llamada": 1,
                    "transcripcion": 1,
                }
            },
        ],
        indent=2,
        ensure_ascii=False,
    )

    return f'''# Ejemplo en Python — MongoDB Driver (PyMongo)
# pip install pymongo

from pymongo import MongoClient

client = MongoClient("mongodb+srv://<usuario>:<password>@<cluster>/")
collection = client["{DB_NAME}"]["{COLLECTION_NAME}"]

pipeline = {pipeline_json}

# Atlas Auto-Embedding vectoriza la query automaticamente con voyage-4.
# No necesitas generar el vector manualmente.
resultados = list(collection.aggregate(pipeline))

for doc in resultados:
    print(doc["id_llamada"], "|", doc["resultado_llamada"], "|", doc["score"])'''


# ---------------------------------------------------------------------------
# Embeddings desde __mdb_internal_search
# ---------------------------------------------------------------------------

def _get_mv_collection_name(index_name: str) -> Optional[str]:
    """
    Encuentra el nombre de la coleccion de embeddings generados
    en __mdb_internal_search para un indice dado.

    Proceso:
    1. $listSearchIndexes sobre la coleccion fuente para obtener el index_id
    2. Busca en __mdb_internal_search la coleccion que empieza con ese index_id
    """
    client = get_client()
    col = client[DB_NAME][COLLECTION_NAME]

    # Obtener el ID del indice
    indexes = list(col.aggregate([{"$listSearchIndexes": {"name": index_name}}]))
    if not indexes:
        return None

    index_id = indexes[0]["id"]

    # Buscar la coleccion interna
    internal_db = client[MDB_INTERNAL_DB]
    all_collections = internal_db.list_collection_names()
    matches = [n for n in all_collections if n.startswith(index_id)]

    if not matches:
        return None

    matches.sort(reverse=True)
    return matches[0]


def _bindata_to_floats(binary_data) -> list:
    """
    Convierte el BinData (Int8Array cuantizado) del auto-embedding a lista de enteros.
    Atlas almacena los embeddings como binario cuantizado (scalar int8).
    """
    try:
        raw = bytes(binary_data)
        # Intentar como int8 (formato scalar quantization)
        n = len(raw)
        values = list(struct.unpack(f"{n}b", raw))
        return values
    except Exception:
        try:
            # Fallback: float32
            raw = bytes(binary_data)
            n = len(raw) // 4
            values = list(struct.unpack(f"{n}f", raw))
            return values
        except Exception:
            return []


def obtener_embedding(doc_id: str) -> dict:
    """
    Obtiene el embedding generado por Auto-Embedding para un documento.
    Accede a __mdb_internal_search directamente.
    """
    mv_collection_name = _get_mv_collection_name(VECTOR_INDEX_NAME)

    if not mv_collection_name:
        return {
            "error": "No se encontro la coleccion de embeddings. El indice puede estar aun construyendose.",
            "tip": f"Verifica con: mongosh '<uri>' --eval 'db.getSiblingDB(\"__mdb_internal_search\").getCollectionNames()'"
        }

    client = get_client()
    internal_db = client[MDB_INTERNAL_DB]
    mv_col = internal_db[mv_collection_name]

    # Buscar por _id (puede ser ObjectId o string)
    try:
        oid = ObjectId(doc_id)
        doc = mv_col.find_one({"_id": oid})
    except Exception:
        doc = mv_col.find_one({"_id": doc_id})

    if not doc:
        return {
            "error": "Embedding no encontrado para este documento. Puede estar aun generandose.",
            "doc_id": doc_id,
            "mv_collection": mv_collection_name
        }

    auto_embed = doc.get("_autoEmbed", {})
    field_data = auto_embed.get(VECTOR_FIELD)

    if field_data is None:
        return {
            "error": f"Campo '_autoEmbed.{VECTOR_FIELD}' no encontrado.",
            "mv_collection": mv_collection_name,
            "campos_disponibles": list(auto_embed.keys())
        }

    values = _bindata_to_floats(field_data)

    return {
        "doc_id": doc_id,
        "mv_collection": mv_collection_name,
        "campo": VECTOR_FIELD,
        "dimensiones": len(values),
        "primeros_10": values[:10],
        "primeros_100": values[:100],
        "vector_completo": values,
        "tipo": "Int8 (scalar quantized)",
        "modelo": "voyage-4 via Atlas Auto-Embedding",
        "base_de_datos_interna": MDB_INTERNAL_DB,
    }


def contar_embeddings_generados() -> dict:
    """
    Cuenta cuantos embeddings han sido generados en __mdb_internal_search.
    Equivalente al comando mongosh de verificacion de la documentacion.
    """
    client = get_client()
    internal_db = client[MDB_INTERNAL_DB]
    import re
    pattern = re.compile(r"^[0-9a-f]{24}-[0-9a-f]{32}-\d+-\d+$")

    try:
        collections = internal_db.list_collection_names()
        mv_collections = [c for c in collections if pattern.match(c)]
        total = sum(internal_db[c].count_documents({}) for c in mv_collections)
        return {
            "total_embeddings": total,
            "colecciones_mv": mv_collections,
            "num_colecciones": len(mv_collections)
        }
    except Exception as e:
        return {"error": str(e), "total_embeddings": 0}


def calcular_similitud_coseno(id1: str, id2: str) -> dict:
    """
    Calcula la similitud coseno entre los embeddings de dos documentos.
    Educativo: muestra la formula y el resultado.
    """
    import math

    emb1 = obtener_embedding(id1)
    emb2 = obtener_embedding(id2)

    if "error" in emb1:
        return {"error": f"Documento 1: {emb1['error']}"}
    if "error" in emb2:
        return {"error": f"Documento 2: {emb2['error']}"}

    v1 = emb1["vector_completo"]
    v2 = emb2["vector_completo"]

    if len(v1) != len(v2):
        return {"error": f"Dimensiones distintas: {len(v1)} vs {len(v2)}"}

    dot = sum(a * b for a, b in zip(v1, v2))
    mag1 = math.sqrt(sum(a * a for a in v1))
    mag2 = math.sqrt(sum(b * b for b in v2))

    if mag1 == 0 or mag2 == 0:
        similitud = 0.0
    else:
        similitud = dot / (mag1 * mag2)

    return {
        "doc_id_1": id1,
        "doc_id_2": id2,
        "similitud_coseno": round(similitud, 6),
        "interpretacion": _interpretar_similitud(similitud),
        "formula": "cos(θ) = (A · B) / (‖A‖ × ‖B‖)",
        "producto_punto": dot,
        "magnitud_1": round(mag1, 4),
        "magnitud_2": round(mag2, 4),
        "dimensiones": len(v1),
    }


def _interpretar_similitud(s: float) -> str:
    if s >= 0.95:
        return "Muy alta similitud - contenido casi identico"
    elif s >= 0.85:
        return "Alta similitud - temas muy relacionados"
    elif s >= 0.70:
        return "Similitud moderada - temas relacionados"
    elif s >= 0.50:
        return "Baja similitud - contenido diferente"
    else:
        return "Muy baja similitud - contenido muy diferente"
