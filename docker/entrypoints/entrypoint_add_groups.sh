#!/bin/bash
SCRIPT_DIR=$(dirname "$0")
. "$SCRIPT_DIR/common.sh"

# ---------------------------------- Helper ---------------------------------- #

validate_and_add_groups() {
    local group_specs
    IFS=',' read -ra group_specs <<< "$1"

    for spec in "${group_specs[@]}"; do
        if [[ "$spec" =~ ^([a-z][a-z0-9_-]*):([0-9]+)$ ]]; then
            local group_name="${BASH_REMATCH[1]}"
            local gid="${BASH_REMATCH[2]}"

            process_group "$group_name" "$gid" || continue
        else
            log_warning "Invalid group specification '$spec', skipping. Format should be 'group_name:gid' where group_name starts with lowercase letter"
        fi
    done
}

process_group() {
    local group_name="$1"
    local gid="$2"

    # Handle existing group
    if existing_group=$(getent group "$group_name" 2>/dev/null); then
        local existing_gid=$(cut -d: -f3 <<< "$existing_group")
        [[ "$existing_gid" != "$gid" ]] && \
            log_warning "Group '$group_name' exists with GID $existing_gid (expected $gid). Using existing group."
        log "Group '$group_name' already exists, skipping creation"
    else
        addgroup -g "$gid" "$group_name" 2>/dev/null || {
            log_warning "Failed to create group '$group_name' with gid $gid"
            return 1
        }
        log "Created group '$group_name' with gid $gid"
    fi

    # Add user to group
    if id -nG beetle 2>/dev/null | grep -qw "$group_name"; then
        log "User beetle is already a member of group '$group_name'"
    else
        adduser beetle "$group_name" 2>/dev/null || {
            log_warning "Failed to add beetle user to group '$group_name'"
            return 1
        }
        log "Added beetle user to group '$group_name'"
    fi
}

# --------------------------------- Main Loop -------------------------------- #

if [[ -n "$EXTRA_GROUPS" ]]; then
    log "Adding extra groups to beetle user: $EXTRA_GROUPS"
    validate_and_add_groups "$EXTRA_GROUPS"
fi

