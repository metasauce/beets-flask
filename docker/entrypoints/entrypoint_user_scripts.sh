#!/bin/bash
SCRIPT_DIR=$(dirname "$0")
. "$SCRIPT_DIR/common.sh"

export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_ROOT_USER_ACTION=ignore

# check for user startup scripts
if [ -f /config/startup.sh ]; then
    log "Running user startup script from /config/startup.sh"
    /config/startup.sh
fi
if [ -f /config/beets-flask/startup.sh ]; then
    log "Running user startup script from /config/beets-flask/startup.sh"
    /config/beets-flask/startup.sh
fi


# check for requirements.txt
if [ -f /config/requirements.txt ]; then
    log "Installing pip requirements from /config/requirements.txt"
    uv pip install -r /config/requirements.txt
fi
if [ -f /config/beets-flask/requirements.txt ]; then
    log "Installing pip requirements from /config/beets-flask/requirements.txt"
    uv pip install -r /config/beets-flask/requirements.txt
fi
