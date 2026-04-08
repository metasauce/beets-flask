
#!/bin/bash
. ./common.sh

log_current_user
log_version_info

cd /repo

mkdir -p /logs
mkdir -p /config/beets
mkdir -p /config/beets-flask

# ------------------------------------------------------------------------------------ #
#                                     start backend                                    #
# ------------------------------------------------------------------------------------ #

# Ignore warnings for production builds
export PYTHONWARNINGS="ignore"


# running the server from inside the backend dir makes imports and redis easier
cd /repo/backend

# Databse creation & migrations (beets-flask)
python -c "from beets_flask.database.migration import run_migrations; run_migrations()"

# Database creation & migration (beets)
python -c "from beets.ui import _open_library; from beets_flask.config.beets_config import get_config; _open_library(get_config().beets_config)"

# Redis server (if not set outside container)
if [ -z "$REDIS_URL" ]; then
  redis-server --daemonize yes >/dev/null 2>&1
fi

# FIXME: Logging is a bit strange for the workers atm a bit of unification could help
python ./launch_redis_workers.py > /logs/redis_workers.log 2>&1
python ./launch_watchdog_worker.py &
redis-cli FLUSHALL >/dev/null 2>&1

# Launch server
sleep 0.5
python ./launch_server.py
