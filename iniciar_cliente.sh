#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Erro: Python 3 nao encontrado."
    exit 1
fi

if ! python3 -m venv --help >/dev/null 2>&1; then
    echo "O modulo venv nao esta instalado. No Ubuntu/Debian, execute:"
    echo "sudo apt install python3-venv"
    exit 1
fi

[ -d venv ] || python3 -m venv venv
source venv/bin/activate

echo "[1/3] Instalando dependencias..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "[2/3] Gerando arquivos Protobuf..."
mkdir -p generated
touch generated/__init__.py
python -m grpc_tools.protoc -I./proto --python_out=./generated --grpc_python_out=./generated ./proto/leilao.proto
sed -i 's/^import leilao_pb2 as/from . import leilao_pb2 as/' generated/leilao_pb2_grpc.py

echo "[3/3] Iniciando cliente..."
python client.py
