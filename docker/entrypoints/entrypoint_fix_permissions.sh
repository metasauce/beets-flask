#!/bin/bash
SCRIPT_DIR=$(dirname "$0")
. "$SCRIPT_DIR/common.sh"

# We want to allow both, USER_ID and PUID (the linuxserver.io convention)
if [ -n "$PUID" ]; then
    USER_ID=$PUID
fi
if [ -n "$PGID" ]; then
    GROUP_ID=$PGID
fi

if [ ! -z "$USER_ID" ] && [ ! -z "$GROUP_ID" ]; then
    log "Fixing permissions as '$(whoami)' with UID $(id -u) and GID $(id -g)"
    log "Setting beetle user to $USER_ID:$GROUP_ID"
    groupmod -g $GROUP_ID beetle
    usermod -u $USER_ID -g $GROUP_ID beetle > /dev/null 2>&1
    log "User beetle now has $(id beetle)"
    find /home/beetle /logs /repo ! -user beetle -exec chown beetle:beetle {} +
    log "Done fixing permissions"
else
    log "No USER_ID and GROUP_ID set, skipping permission updates"
fi

# add groups
. "$SCRIPT_DIR/entrypoint_add_groups.sh"
