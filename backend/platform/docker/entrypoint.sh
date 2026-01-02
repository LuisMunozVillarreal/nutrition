#!/bin/bash

set -eux -o pipefail

source $SRC_DIR/.venv/bin/activate

./manage.py migrate
./manage.py collectstatic --no-input


# Start services
# Removed nginx and supervisord to allow running as non-root (UID 1001)

# Start Gunicorn directly
exec gunicorn config.wsgi:application --bind 0.0.0.0:9000 --workers 3
