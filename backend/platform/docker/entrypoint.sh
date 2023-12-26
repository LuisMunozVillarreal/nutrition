#!/bin/bash

set -eux -o pipefail

source /home/$USER_NAME/.cache/pypoetry/virtualenvs/nutrition-*/bin/activate

./manage.py migrate
./manage.py collectstatic --no-input

# Start services
sudo ntpd
sudo service nginx start

# Star django
sudo -E env PATH=$PATH supervisord -n -c /etc/supervisor/supervisord.conf "$@"
