#!/bin/bash
. ./docker/entrypoints/common.sh

log_current_user
log_version_info
log "Starting development environment..."

cd /repo/frontend

# pnpm run build:dev &  # use this for debugging with ios, port 5001 (no cors allowed)
pnpm run dev & # normal dev, port 5173
vite_pid=$!
sleep 3  # Give Vite a moment to start
if ! kill -0 $vite_pid 2>/dev/null; then
    log_warning "starting vite failed, will try to fix this by installing dependencies ..."
    pnpm install
    pnpm run dev &
fi


cd /repo

mkdir -p /repo/log
rm /repo/log/for_web.log >/dev/null 2>&1
rm /repo/frontend/vite.config.ts.timestamp-*.mjs >/dev/null 2>&1

mkdir -p /config/beets
mkdir -p /config/beets-flask

export FLASK_ENV=development
export FLASK_DEBUG=1

# ------------------------------------------------------------------------------------ #
#                                     start backend                                    #
# ------------------------------------------------------------------------------------ #

# running the server from inside the backend dir makes imports and redis easier
cd /repo/backend

redis-server --daemonize yes


# blocking
python ./launch_db_init.py
python ./launch_redis_workers.py

# keeps running in the background
python ./launch_watchdog_worker.py &

redis-cli FLUSHALL


# generate types for the frontend (only done in dev mode)
python ./generate_types.py

# we need to run with one worker for socketio to work (but need at least threads for SSEs)
# sufficient timout for the interactive import sessions, which may take a couple of minutes
# gunicorn --worker-class eventlet -w 1 --threads 32  --timeout 300 --bind 0.0.0.0:5001 --reload 'main:create_app()'


# see for available cli options:
# https://www.uvicorn.org/#command-line-options
uvicorn beets_flask.server.app:create_app --port 5001 \
    --host 0.0.0.0 \
    --factory \
    --workers 1 \
    --use-colors \
    --reload



# if we need to debug the continaer without running the webserver:
# tail -f /dev/null
