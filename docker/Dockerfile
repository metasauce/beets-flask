FROM python:3.12-slim AS base

FROM base AS deps

# Create user and group
RUN groupadd -g 1000 beetle && \
    useradd -m -u 1000 -g beetle beetle


ENV HOSTNAME="beets-container"
ENV EDITOR="vi"
# need to set some cli editor so `beet edit` works, vi comes with alpine

# map beets directory and our configs to /config
RUN mkdir -p /config/beets /config/beets-flask /logs && \
    chown -R beetle:beetle /config /logs

ENV BEETSDIR="/config/beets"
ENV BEETSFLASKDIR="/config/beets-flask"
ENV BEETSFLASKLOG="/logs/beets-flask.log"

# our default folders they should not be used in production
RUN mkdir -p /music/inbox /music/imported && \
    chown -R beetle:beetle /music

# dependencies
RUN apt update
RUN --mount=type=cache,target=/var/cache/apt \
    apt install -y --no-install-recommends \
    imagemagick \
    redis  \
    bash \
    tmux \
    git \
    ffmpeg


# Install backend dependencies

# Prevent __pycache__ directories
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
# avoid creating a venv with uv, use system python
ENV UV_PROJECT_ENVIRONMENT="/usr/local/"

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir uv


WORKDIR /repo/backend
COPY ./backend/pyproject.toml /repo/backend/
COPY ./README.md /repo/

RUN uv sync --no-install-project

# Install our package (backend)
COPY ./backend/beets_flask/ /repo/backend/beets_flask/
COPY ./backend/generate_types.py /repo/backend/
COPY ./backend/launch_redis_workers.py /repo/backend/
COPY ./backend/launch_watchdog_worker.py /repo/backend/
COPY ./backend/launch_db_init.py /repo/backend/

RUN uv sync

# Extract version from pyproject.toml
RUN mkdir -p /version
RUN python -c "import tomllib; print(tomllib.load(open('/repo/backend/pyproject.toml', 'rb'))['project']['version'])" > /version/backend.txt

# ------------------------------------------------------------------------------------ #
#                                      Development                                     #
# ------------------------------------------------------------------------------------ #

FROM deps AS dev

RUN --mount=type=cache,target=/var/cache/apt \
    apt install -y --no-install-recommends \
    npm

RUN npm install -g pnpm
RUN pnpm config set store-dir /repo/frontend/.pnpm-store

# Copy the lock files and install dependencies
WORKDIR /repo
COPY ./frontend/package.json /repo/frontend/
COPY ./frontend/pnpm-lock.yaml /repo/frontend/

WORKDIR /repo/frontend
# RUN pnpm i

# Extract version from package.json
RUN mkdir -p /version
RUN python -c "import json; print(json.load(open('/repo/frontend/package.json'))['version'])" \
    > /version/frontend.txt

ENV IB_SERVER_CONFIG="dev_docker"

# relies on mounting this volume
WORKDIR /repo
USER root
ENTRYPOINT [ \
    "/bin/sh", "-c", \
    "./docker/entrypoints/entrypoint_fix_permissions.sh && \ 
     ./docker/entrypoints/entrypoint_user_scripts.sh && \
    su beetle -c ./docker/entrypoints/entrypoint_dev.sh" \
    ]


# ------------------------------------------------------------------------------------ #
#                                         Build                                        #
# ------------------------------------------------------------------------------------ #

FROM deps AS build
# Build frontend files

RUN --mount=type=cache,target=/var/cache/apt \
    apt install -y --no-install-recommends \
    npm

RUN npm install -g pnpm
RUN pnpm config set store-dir /repo/frontend/.pnpm-store

WORKDIR /repo
COPY ./frontend ./frontend/
RUN chown -R beetle:beetle /repo

# Extract version from package.json
RUN mkdir -p /version
RUN python -c "import json; print(json.load(open('/repo/frontend/package.json'))['version'])" \
    > /version/frontend.txt

USER beetle
WORKDIR /repo/frontend
# RUN --mount=type=cache,id=pnpm-store,target=/root/.local/share/pnpm/store \
RUN pnpm install
RUN pnpm run build



# ------------------------------------------------------------------------------------ #
#                                      Production                                      #
# ------------------------------------------------------------------------------------ #

FROM deps AS prod

ENV IB_SERVER_CONFIG="prod"

WORKDIR /repo
COPY --from=build /repo/frontend/dist /repo/frontend/dist
COPY --from=build /version /version
COPY docker/entrypoints .
RUN chown -R beetle:beetle /repo

USER root

ENTRYPOINT [ \
    "/bin/sh", "-c", \
    "/repo/entrypoint_fix_permissions.sh && \
    /repo/entrypoint_user_scripts.sh && \
    su beetle -c /repo/entrypoint.sh" \
    ]


