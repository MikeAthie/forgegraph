#!/bin/bash
# Generate Python protobuf code from the engine proto file
#
# Usage: ./scripts/generate_proto.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
ENGINE_DIR="$(dirname "$BACKEND_DIR")/engine"
PROTO_FILE="$ENGINE_DIR/proto/engine.proto"
OUTPUT_DIR="$BACKEND_DIR/infrastructure/grpc"

echo "Generating Python protobuf code..."
echo "Proto file: $PROTO_FILE"
echo "Output directory: $OUTPUT_DIR"

# Ensure output directory exists
mkdir -p "$OUTPUT_DIR"

# Generate Python code
python -m grpc_tools.protoc \
    -I"$ENGINE_DIR/proto" \
    --python_out="$OUTPUT_DIR" \
    --grpc_python_out="$OUTPUT_DIR" \
    "$PROTO_FILE"

# Create __init__.py if it doesn't exist
touch "$OUTPUT_DIR/__init__.py"

echo "Generated:"
ls -la "$OUTPUT_DIR"

echo "Done!"
