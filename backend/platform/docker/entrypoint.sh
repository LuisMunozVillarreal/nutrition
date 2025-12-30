#!/bin/bash

set -eux -o pipefail

source $SRC_DIR/.venv/bin/activate

./manage.py migrate
./manage.py collectstatic --no-input

# Start supervisord directly
exec supervisord -n -c /etc/supervisor/supervisord.conf "$@"
