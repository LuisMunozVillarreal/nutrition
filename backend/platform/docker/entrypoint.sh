#!/bin/bash

set -eux -o pipefail

source $SRC_DIR/.venv/bin/activate

./manage.py migrate
./manage.py collectstatic --no-input


# Start services
# Removed sudo, running as non-root (UID 1001)
# Nginx and Supervisord are configured to use /tmp for pids/sockets

# Start supervisord directly
exec supervisord -n -c /etc/supervisor/supervisord.conf "$@"
