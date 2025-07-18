#!/usr/bin/env bash
# Compile ALL .proto files under $PROTO_DIR into $OUT_DIR.
# Usage: ./gen_protos.sh [proto_dir] [out_dir]

set -euo pipefail                               # fail fast on any error

PROTO_DIR="${1:-proto}"
OUT_DIR="${2:-app/proto_gen}"

mkdir -p "${OUT_DIR}"

# Generate stubs: *_pb2.py + *_pb2_grpc.py (+ optional *.pyi type hints)
python -m grpc_tools.protoc \
  -I "${PROTO_DIR}" \
  --python_out="${OUT_DIR}" \
  --grpc_python_out="${OUT_DIR}" \
  $(find "${PROTO_DIR}" -type f -name '*.proto')

# Make it a proper Python package
touch "${OUT_DIR}/__init__.py"

echo "✅ Protobufs compiled to ${OUT_DIR}"
