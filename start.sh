#!/bin/bash
# ============================================================
# Voice Demo — Script de arranque
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"

# El .venv se guarda fuera de Google Drive para evitar que la sincronizacion
# de Drive provoque reinicios infinitos del servidor en modo --reload.
# Usamos un hash del path para que cada proyecto tenga su propio venv.
VENV_BASE="$HOME/.venvs/voices-demo"
VENV="$VENV_BASE"

echo ""
echo "  MongoDB Vector Search — Voice Demo"
echo "  ==================================="
echo ""

# Verificar .env
if [ ! -f "$BACKEND_DIR/.env" ]; then
  if [ -f "$SCRIPT_DIR/.env.example" ]; then
    echo "  [!] No se encontro .env en backend/"
    echo "      Copia .env.example a backend/.env y configura MONGODB_URI"
    echo ""
    echo "      cp .env.example backend/.env"
    echo ""
    exit 1
  fi
fi

# Crear venv si no existe
if [ ! -d "$VENV" ]; then
  echo "  [→] Creando entorno virtual Python en $VENV ..."
  mkdir -p "$HOME/.venvs"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt"
  echo "  [✓] Dependencias instaladas"
fi

# Arrancar backend
echo "  [→] Iniciando backend FastAPI en http://localhost:8000"
echo "  [→] Abre tu navegador en:  http://localhost:8000"
echo ""
echo "  Presiona Ctrl+C para detener"
echo ""

cd "$BACKEND_DIR"
# --reload-dir apunta solo al codigo fuente (no al venv).
# El venv vive fuera de Google Drive, por lo que sus archivos nunca
# desencadenaran un reload al ser sincronizados por Drive.
"$VENV/bin/uvicorn" main:app --host 0.0.0.0 --port 8000 --reload \
  --reload-dir "$BACKEND_DIR"
