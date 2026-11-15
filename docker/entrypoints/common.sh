#!/bin/bash
# A number of common functions used by entrypoints
log() {
    printf "[Entrypoint] $1\n"
}

log_error() {
    printf "\033[0;31m[Entrypoint] $1\033[0m\n" >&2
}

log_warning() {
    printf "\033[0;33m[Entrypoint] $1\033[0m\n"
}

log_current_user() {
    log "Running as '$(whoami)' with UID $(id -u) and GID $(id -g)"
    log "Current working directory: $(pwd)"
}

log_version_info() {
    log "Version info:"
    log "  Backend:  $BACKEND_VERSION"
    log "  Frontend: $FRONTEND_VERSION"
    log "  Mode:     $IB_SERVER_CONFIG"
}

get_version_info() {
    if [ -f /version/backend.txt ]; then
        export BACKEND_VERSION=$(cat /version/backend.txt)
    else
        export BACKEND_VERSION="unk"
    fi
    
    if [ -f /version/frontend.txt ]; then
        export FRONTEND_VERSION=$(cat /version/frontend.txt)
    else
        export FRONTEND_VERSION="unk"
    fi
}

# Populate the environment variables for the version info
get_version_info
