#!/bin/sh
# Generate the demo dataset on first boot (the data volume starts empty).
set -e

if [ ! -f "$HALFCA_DATA_DIR/halfca.duckdb" ] && python -c "import halfca.data.build" 2>/dev/null; then
    echo "[entrypoint] no database yet: generating the demo dataset"
    python -m halfca.data.build --scenario demo
fi

exec "$@"
