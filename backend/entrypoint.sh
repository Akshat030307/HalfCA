#!/bin/sh
# Generate the demo dataset on first boot (the data volume starts empty).
set -e

# (Re)build the demo dataset when there is none or it was made by older code.
python -m halfca.data.build --scenario demo --if-stale

exec "$@"
