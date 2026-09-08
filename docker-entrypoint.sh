#!/bin/sh
# FLIPUS — entrypoint single-container.
# Substitusi port nginx dari env PORT (di-set Railway/Render), lalu start supervisord.
set -e

PORT="${PORT:-8000}"

# Ganti placeholder __PORT__ di nginx config dgn nilai PORT
if [ -f /etc/nginx/conf.d/default.conf ]; then
    sed -i "s/__PORT__/${PORT}/g" /etc/nginx/conf.d/default.conf
fi

exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf
