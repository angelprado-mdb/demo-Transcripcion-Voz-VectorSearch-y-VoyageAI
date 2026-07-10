# Voice Demo — MongoDB Atlas Vector Search

Demo interactivo que muestra cómo MongoDB Atlas transforma transcripciones de llamadas comerciales en vectores semánticos usando **Auto-Embedding con VoyageAI**, permite buscarlas por significado y construye un pipeline RAG completo con LLM de tu elección.

## ¿Qué demuestra?

| Capacidad | Descripción |
|---|---|
| **Auto-Embedding** | Atlas genera y gestiona los vectores automáticamente al insertar documentos, sin código adicional |
| **Vector Search** | Búsqueda semántica en lenguaje natural usando `$vectorSearch` con modelo `voyage-4` |
| **Embeddings internos** | Visualización de los vectores almacenados en `__mdb_internal_search` |
| **RAG** | Pipeline completo Retrieve → Augment → Generate con OpenAI, Anthropic o Gemini |

## Arquitectura

```
┌─────────────────────────────────────────────────────────┐
│  Frontend (HTML/CSS/JS — Wizard de pantalla completa)   │
│  http://localhost:8000                                  │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP
┌────────────────────────▼────────────────────────────────┐
│  Backend (FastAPI — Python)                             │
│  /api/llamadas/upload   → Insertar llamadas             │
│  /api/llamadas/search   → $vectorSearch                 │
│  /api/llamadas/{id}/embedding → Ver vector              │
│  /api/chat              → RAG completo                  │
└────────────────────────┬────────────────────────────────┘
                         │ PyMongo
┌────────────────────────▼────────────────────────────────┐
│  MongoDB Atlas                                          │
│  DB: Llamadas  |  Colección: Llamadas                   │
│  Índice: vector_index (autoEmbed, voyage-4)             │
│  Embeddings: __mdb_internal_search (interno Atlas)      │
└─────────────────────────────────────────────────────────┘
```

---

## Requisitos previos

- Python 3.11 o superior
- Cuenta en [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register) (el tier gratuito M0 es suficiente)
- Una API Key de alguno de estos proveedores LLM (solo para el paso de Chat RAG):
  - [OpenAI](https://platform.openai.com/api-keys)
  - [Anthropic](https://console.anthropic.com/)
  - [Google AI Studio](https://aistudio.google.com/app/apikey)

---

## Paso 1 — Crear el Cluster en MongoDB Atlas

1. Ve a [cloud.mongodb.com](https://cloud.mongodb.com) e inicia sesión.

2. Haz clic en **"Create"** y elige **M0 Free Tier** (o cualquier tier pagado).

3. Elige proveedor de nube y región, ponle un nombre al cluster y haz clic en **"Create Deployment"**.

4. En el asistente de conexión:
   - Crea un usuario de base de datos: anota el **usuario** y **contraseña**.
   - Agrega tu IP actual a la lista de acceso (o usa `0.0.0.0/0` para acceso desde cualquier lugar durante el demo).

5. Haz clic en **"Connect"** → **"Drivers"** → selecciona **Python** → copia la connection string. Tendrá este formato:
   ```
   mongodb+srv://<usuario>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority
   ```

---

## Paso 2 — Crear la base de datos y colección

Desde **Atlas UI → Browse Collections**:

1. Haz clic en **"Add My Own Data"** (o **"Create Database"** si ya tienes otras).
2. Ingresa:
   - **Database name:** `Llamadas`
   - **Collection name:** `Llamadas`
3. Haz clic en **"Create"**.

> También puedes hacerlo desde **mongosh** o **MongoDB Compass** — la colección se crea automáticamente al insertar el primer documento desde la app.

---

## Paso 3 — Importar los datos de ejemplo (opcional)

El repositorio incluye archivos JSON de muestra con transcripciones de llamadas comerciales. Puedes importarlos con **mongoimport** antes de arrancar la app:

```bash
# Una sola llamada
mongoimport --uri "mongodb+srv://<usuario>:<password>@<cluster>.mongodb.net" \
  --db Llamadas \
  --collection Llamadas \
  --file transcripcion_llamada_seguros.json

# Múltiples llamadas (array JSON)
mongoimport --uri "mongodb+srv://<usuario>:<password>@<cluster>.mongodb.net" \
  --db Llamadas \
  --collection Llamadas \
  --file 5_transcripciones_adicionales.json \
  --jsonArray
```

> **mongoimport** viene incluido en [MongoDB Database Tools](https://www.mongodb.com/try/download/database-tools).

Alternativamente, puedes subir los archivos directamente desde la interfaz de la app en el **Paso 1 del wizard**.

---

## Paso 4 — Crear el índice de Vector Search con Auto-Embedding

Este es el paso clave. El índice `autoEmbed` le indica a Atlas que vectorice automáticamente el campo `transcripcion_texto` usando VoyageAI `voyage-4` cada vez que se inserte o actualice un documento.

### Opción A — Desde Atlas UI (recomendado)

1. En tu cluster, ve a la pestaña **"Atlas Search"** (en el menú lateral izquierdo).
2. Haz clic en **"Create Search Index"**.
3. Selecciona **"Atlas Vector Search"** → **"JSON Editor"**.
4. Elige la base de datos `Llamadas` y la colección `Llamadas`.
5. Pega la siguiente definición y haz clic en **"Next"** → **"Create Search Index"**:

```json
{
  "fields": [
    {
      "type": "autoEmbed",
      "modality": "text",
      "path": "transcripcion_texto",
      "model": "voyage-4"
    }
  ]
}
```

6. Asegúrate de que el nombre del índice sea exactamente **`vector_index`**.
7. Espera a que el status cambie de `BUILDING` a **`READY`** (tarda ~1 minuto en clusters vacíos).

### Opción B — Desde mongosh

```javascript
use Llamadas

db.Llamadas.createSearchIndex({
  name: "vector_index",
  type: "vectorSearch",
  definition: {
    fields: [
      {
        type: "autoEmbed",
        modality: "text",
        path: "transcripcion_texto",
        model: "voyage-4"
      }
    ]
  }
})
```

### Opción C — Desde Python (PyMongo)

```python
from pymongo import MongoClient

client = MongoClient("mongodb+srv://<usuario>:<password>@<cluster>.mongodb.net/")
collection = client["Llamadas"]["Llamadas"]

collection.create_search_index({
    "name": "vector_index",
    "type": "vectorSearch",
    "definition": {
        "fields": [
            {
                "type": "autoEmbed",
                "modality": "text",
                "path": "transcripcion_texto",
                "model": "voyage-4"
            }
        ]
    }
})
```

### Verificar que los embeddings se generaron

Una vez que el índice esté `READY` y hayas insertado documentos, verifica que Atlas generó los embeddings:

```javascript
// En mongosh
mongosh "<connection-string>" --eval '
  print("Embeddings generados: " +
    db.getSiblingDB("__mdb_internal_search")
      .getCollectionNames()
      .filter(c => /^[0-9a-f]{24}-[0-9a-f]{32}-\d+-\d+$/.test(c))
      .map(c => db.getSiblingDB("__mdb_internal_search").getCollection(c).countDocuments())
      .reduce((a, b) => a + b, 0)
  );
'
```

El resultado debe ser igual al número de documentos en tu colección.

> **Nota importante:** Con `autoEmbed`, Atlas gestiona los vectores completamente. No necesitas modificar tu aplicación para generar embeddings — simplemente insertas documentos con `insert_one()` o `insert_many()` como siempre.

---

## Paso 5 — Configurar y ejecutar la aplicación

### Clonar el repositorio

```bash
git clone <url-del-repositorio>
cd voices-demo
```

### Configurar variables de entorno

```bash
cp .env.example backend/.env
```

Edita `backend/.env` y completa con tus valores:

```env
# Connection string de Atlas (del Paso 1)
MONGODB_URI=mongodb+srv://<usuario>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority

# Base de datos y colección (deben coincidir con lo creado en el Paso 2)
DB_NAME=Llamadas
COLLECTION_NAME=Llamadas

# Nombre exacto del índice creado en el Paso 4
VECTOR_INDEX_NAME=vector_index

# Campo de texto que usa el índice para Auto-Embedding
VECTOR_FIELD=transcripcion_texto
```

### Ejecutar con el script de arranque

```bash
chmod +x start.sh
./start.sh
```

El script automáticamente:
- Crea un entorno virtual Python en `backend/.venv`
- Instala todas las dependencias de `requirements.txt`
- Inicia el servidor FastAPI en `http://localhost:8000`

Abre tu navegador en **http://localhost:8000**.

### Ejecución manual (alternativa)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate          # En Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload --reload-dir .
```

---

## Estructura del proyecto

```
voices-demo/
├── start.sh                        # Script de arranque (crea venv, instala deps, ejecuta)
├── .env.example                    # Plantilla de variables de entorno
│
├── backend/
│   ├── .env                        # Variables de entorno (no subir a git)
│   ├── requirements.txt            # Dependencias Python
│   ├── main.py                     # FastAPI — endpoints REST
│   ├── database.py                 # PyMongo — operaciones MongoDB + __mdb_internal_search
│   └── rag.py                      # Lógica RAG: Retrieve → Augment → Generate
│
├── frontend/
│   ├── index.html                  # SPA — Wizard de 7 pasos
│   ├── style.css                   # Tema claro, paleta MongoDB
│   └── app.js                      # Lógica del wizard, búsqueda, chat, embeddings
│
└── [archivos JSON de muestra]      # Transcripciones de llamadas para el demo
```

---

## Endpoints de la API

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/health` | Estado de conexión y conteo de embeddings |
| `GET` | `/api/modelos` | Modelos LLM disponibles por proveedor |
| `POST` | `/api/llamadas/upload` | Inserta JSON (objeto o array) en MongoDB |
| `GET` | `/api/llamadas/` | Lista todas las llamadas |
| `GET` | `/api/llamadas/{id}` | Obtiene una llamada por `_id` |
| `DELETE` | `/api/llamadas/{id}` | Elimina una llamada |
| `POST` | `/api/llamadas/search` | Búsqueda semántica con `$vectorSearch` |
| `GET` | `/api/llamadas/{id}/embedding` | Vector desde `__mdb_internal_search` |
| `POST` | `/api/llamadas/similitud` | Similitud coseno entre dos llamadas |
| `GET` | `/api/embeddings/estado` | Estado de los embeddings generados |
| `POST` | `/api/chat` | RAG completo (Retrieve + Augment + Generate) |

La documentación interactiva de la API está disponible en `http://localhost:8000/docs` (Swagger UI).

---

## Schema del JSON de llamadas

La app acepta cualquier JSON que contenga el campo `transcripcion` (array de turnos). Al insertar, genera automáticamente el campo `transcripcion_texto` (string plano) que usa el índice para vectorizar.

```json
{
  "id_llamada": "CALL-2026-MMDD-XXX",
  "fecha": "2026-07-10",
  "hora_inicio": "10:30:00",
  "duracion_segundos": 285,
  "empresa": "Mi Empresa SA",
  "agente": {
    "nombre": "Nombre del Agente",
    "departamento": "Ventas",
    "puesto": "Asesor Senior"
  },
  "cliente": {
    "nombre": "Nombre del Cliente",
    "telefono": "+52 55 5555 0000",
    "correo": "cliente@example.com"
  },
  "producto": {
    "nombre": "Producto X",
    "costo_mensual_mxn": 450
  },
  "resultado_llamada": "Venta Cerrada / Venta Perdida / Llamar más tarde",
  "transcripcion": [
    {
      "orden": 1,
      "hablante": "Agente",
      "rol": "Agente",
      "tiempo_marca": "00:00",
      "texto": "Buenos días, ¿hablo con...?"
    },
    {
      "orden": 2,
      "hablante": "Cliente",
      "rol": "Cliente",
      "texto": "Sí, con el mismo."
    }
  ]
}
```

> El schema es flexible — el cliente final puede adaptarlo a su estructura. El único campo requerido para que funcione el Vector Search es `transcripcion` (array con objetos que tengan un campo `texto`).

---

## Cómo funciona el Auto-Embedding

```
Tu JSON
  └─► insert_one(doc)                 ← Tu aplicación, sin cambios
        └─► MongoDB Atlas              ← Almacena el documento
              └─► Detecta via índice autoEmbed
                    └─► VoyageAI voyage-4  ← Genera el vector
                          └─► __mdb_internal_search  ← Atlas almacena el vector
                                                         separado de tus datos
```

**Lo que NO necesitas hacer:**
- Llamar a la API de VoyageAI manualmente
- Agregar un campo de vector al documento
- Mantener los vectores sincronizados al actualizar
- Gestionar versiones del modelo de embeddings

**Lo que sí necesitas:**
- Definir el índice `autoEmbed` una sola vez en Atlas UI (Paso 4)
- Insertar documentos con el campo `transcripcion_texto` (string de texto plano)

---

## Proveedores LLM soportados para el Chat RAG

El paso de generación del RAG soporta tres proveedores. La API Key se pasa en cada petición y nunca se almacena en el servidor.

| Proveedor | Modelos disponibles | Obtener API Key |
|---|---|---|
| **OpenAI** | `gpt-4o`, `gpt-4o-mini` | [platform.openai.com](https://platform.openai.com/api-keys) |
| **Anthropic** | `claude-3-5-sonnet`, `claude-3-5-haiku` | [console.anthropic.com](https://console.anthropic.com/) |
| **Google Gemini** | `gemini-2.0-flash`, `gemini-2.5-flash-preview`, `gemini-1.5-pro-002` | [aistudio.google.com](https://aistudio.google.com/app/apikey) |

---

## Solución de problemas comunes

### El servidor se reinicia en loop al arrancar

El watcher de uvicorn detecta cambios en `.venv/`. El script `start.sh` ya incluye `--reload-dir` para evitar esto. Si ejecutas manualmente, usa:

```bash
uvicorn main:app --reload --reload-dir .
```

### Vector Search no retorna resultados

Verifica que:
1. El índice `vector_index` existe y su estado es `READY` (Atlas UI → Atlas Search).
2. El campo `VECTOR_FIELD` en `.env` es `transcripcion_texto` (no `transcripcion`).
3. Los documentos tienen el campo `transcripcion_texto` — si los importaste con `mongoimport` antes de crear la app, ejecuta este script para agregarlo:

```python
from pymongo import MongoClient
client = MongoClient("mongodb+srv://...")
col = client["Llamadas"]["Llamadas"]

for doc in col.find({}):
    if "transcripcion_texto" not in doc and "transcripcion" in doc:
        turnos = doc["transcripcion"]
        texto = "\n".join(
            f"{t.get('hablante','')}: {t.get('texto','')}"
            for t in turnos if isinstance(t, dict)
        )
        col.update_one({"_id": doc["_id"]}, {"$set": {"transcripcion_texto": texto}})

print("Actualización completa")
```

### Error de Gemini: `404 model not found`

Asegúrate de estar usando los nombres de modelo correctos. Los modelos `gemini-1.5-flash` y `gemini-1.5-pro` (sin sufijo) ya no están disponibles. Usa:
- `gemini-2.0-flash` (recomendado)
- `gemini-2.5-flash-preview-05-20`
- `gemini-1.5-pro-002`

### `style.css` o `app.js` dan 404

El servidor FastAPI sirve los archivos estáticos directamente. Verifica que el directorio `frontend/` existe relativo a `backend/`. La ruta esperada es `../frontend/` desde el directorio `backend/`.

---

## Dependencias principales

```
fastapi==0.115.0          # Framework web
uvicorn[standard]==0.30.6  # Servidor ASGI
pymongo[srv]==4.10.1       # Driver de MongoDB
python-dotenv==1.0.1       # Variables de entorno
openai==1.51.0             # SDK OpenAI
anthropic==0.34.2          # SDK Anthropic
google-genai>=1.0.0        # SDK Google Gemini (nuevo SDK oficial)
httpx==0.27.2              # HTTP client async
```

---

## Recursos

- [MongoDB Atlas Vector Search — Documentación](https://www.mongodb.com/docs/vector-search/)
- [Auto-Embedding Overview](https://www.mongodb.com/docs/vector-search/crud-embeddings/automated-embedding/)
- [VoyageAI — Modelos de Embedding](https://docs.voyageai.com/docs/introduction)
- [Aggregation Pipeline — $vectorSearch](https://www.mongodb.com/docs/vector-search/query/aggregation-stages/vector-search-stage/)
- [PyMongo Driver](https://www.mongodb.com/docs/drivers/pymongo/)
