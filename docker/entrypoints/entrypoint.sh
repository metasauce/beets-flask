
#!/bin/sh
source ./common.sh

log_current_user
log_version_info

cd /repo

mkdir -p /repo/log
mkdir -p /config/beets
mkdir -p /config/beets-flask

# ------------------------------------------------------------------------------------ #
#                                     start backend                                    #
# ------------------------------------------------------------------------------------ #

# Ignore warnings for production builds
export PYTHONWARNINGS="ignore"

# running the server from inside the backend dir makes imports and redis easier
cd /repo/backend

# Redis: quando REDIS_URL esta definido usamos o redis compartilhado (producao),
# caso contrario subimos um redis local (dev).
if [ -n "${REDIS_URL:-}" ]; then
    log "Using external redis (host: $(echo "$REDIS_URL" | sed -E 's#.*@([^/]+).*#\1#'))"
else
    redis-server --daemonize yes >/dev/null 2>&1
fi


# blocking
python ./launch_db_init.py
python ./launch_redis_workers.py > /logs/redis_workers.log 2>&1

# keeps running in the background
python ./launch_watchdog_worker.py &

# Limpa apenas o nosso db. Nunca FLUSHALL: o redis e compartilhado e
# apagaria as filas do celery de outros projetos.
if [ -n "${REDIS_URL:-}" ]; then
    redis-cli -u "$REDIS_URL" FLUSHDB >/dev/null 2>&1
else
    redis-cli FLUSHALL >/dev/null 2>&1
fi

# we need to run with one worker for socketio to work
uvicorn beets_flask.server.app:create_app --port 5001 \
    --host 0.0.0.0 \
    --factory \
    --workers 4 \
    --use-colors \
    --log-level info \
    --no-access-log
