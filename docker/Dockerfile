# ------------------------------ Builder ffmpeg ------------------------------ #

# FFMPEG comes with a ton of dependencies (e.g. llvm)
# the full install is over 400mb...
# we use a static version which is only 50mb
FROM debian:trixie-slim AS builder_ffmpeg

# Install required tools
RUN --mount=type=cache,sharing=locked,target=/var/cache/apt \
    apt-get update && apt-get install -y --no-install-recommends \
        xz-utils \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp
RUN mkdir -p /tmp/ffmpeg
ARG TARGETARCH
RUN curl -L https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-${TARGETARCH}-static.tar.xz \
    | tar -xJ -C /tmp/ffmpeg --strip-components=1


# ------------------------------ Builder python ------------------------------ #

FROM ghcr.io/astral-sh/uv:python3.12-trixie-slim AS builder_py
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /repo/backend
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_NO_DEV=1
ENV UV_PYTHON_DOWNLOADS=0

# Install backend dependencies
COPY ./backend/pyproject.toml ./backend/uv.lock /repo/backend/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project

# Install backend package
COPY ./README.md /repo/
COPY ./backend/beets_flask/ /repo/backend/beets_flask/
COPY ./backend/generate_types.py /repo/backend/
COPY ./backend/launch_*.py /repo/backend/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

# Extract version from pyproject.toml
RUN mkdir -p /version
RUN python -c "import tomllib; print(tomllib.load(open('/repo/backend/pyproject.toml', 'rb'))['project']['version'])" > /version/backend.txt

# ------------------------------- Builder node ------------------------------- #

FROM node:22-slim AS builder_node

# Install pnpm
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable

COPY ./frontend /repo/frontend/

WORKDIR /repo/frontend
RUN --mount=type=cache,sharing=locked,id=pnpm,target=/pnpm/store \
    pnpm install --frozen-lockfile

# Extract version from package.json
RUN mkdir -p /version
RUN node -p "require('/repo/frontend/package.json').version" > /version/frontend.txt

RUN pnpm run build


# ---------------------------------------------------------------------------- #
#                                     Base                                     #
# ---------------------------------------------------------------------------- #

FROM python:3.12-slim-trixie AS base
COPY --from=builder_py /bin/uv /bin/uvx /bin/

ENV HOSTNAME="beets-container"
ENV EDITOR="vi"
# need to set some cli editor so `beet edit` works, vi comes with slim
ENV BEETSDIR="/config/beets"
ENV BEETSFLASKDIR="/config/beets-flask"
ENV BEETSFLASKLOG="/logs/beets-flask.log"
ENV PATH="/repo/backend/.venv/bin:$PATH"

# Create user and group
RUN groupadd -g 1000 beetle && \
    useradd -m -u 1000 -g beetle beetle

# map beets directory and our configs to /config
RUN mkdir -p /config/beets /config/beets-flask /logs && \
    chown -R beetle:beetle /config /logs

# our default folders they should not be used in production
RUN mkdir -p /music/inbox /music/imported && \
    chown -R beetle:beetle /music

# Install dependencies:
RUN --mount=type=cache,sharing=locked,target=/var/cache/apt \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    redis \
    tmux \
    imagemagick && \
    rm -rf /var/lib/apt/lists/*

# Copy only the binaries from builder
COPY --from=builder_ffmpeg /tmp/ffmpeg/ffmpeg /usr/local/bin/ffmpeg
COPY --from=builder_ffmpeg /tmp/ffmpeg/ffprobe /usr/local/bin/ffprobe
RUN ffmpeg -version

# ------------------------------------------------------------------------------------ #
#                                      Production                                      #
# ------------------------------------------------------------------------------------ #

FROM base AS prod

ENV IB_SERVER_CONFIG="prod"

WORKDIR /repo
COPY --from=builder_node --chown=beetle:beetle /repo/frontend/dist /repo/frontend/dist
COPY --from=builder_node --chown=beetle:beetle /version/frontend.txt /version/frontend.txt
COPY --from=builder_py --chown=beetle:beetle /repo/backend/ /repo/backend/
COPY --from=builder_py --chown=beetle:beetle /version/backend.txt /version/backend.txt

COPY --chown=beetle:beetle ./docker/entrypoints/*.sh /repo/
RUN chmod +x /repo/*.sh

USER root

ENTRYPOINT [ \
    "/bin/bash", "-c", \
    "/repo/entrypoint_fix_permissions.sh && \
    /repo/entrypoint_user_scripts.sh && \
    su beetle -c /repo/entrypoint.sh" \
    ]


# ------------------------------------------------------------------------------------ #
#                                      Development                                     #
# ------------------------------------------------------------------------------------ #

FROM base AS dev

ENV IB_SERVER_CONFIG="dev_docker"
ENV UV_LINK_MODE=copy

RUN --mount=type=cache,sharing=locked,target=/var/cache/apt \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install nodejs
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
RUN apt-get install -y nodejs

# Install pnpm
RUN npm install --global corepack@latest
RUN corepack enable pnpm
RUN corepack use pnpm@latest-10

# Copy the lock files and install dependencies
WORKDIR /repo
COPY ./frontend/package.json ./frontend/pnpm-lock.yaml /repo/frontend/
COPY ./backend/pyproject.toml ./backend/uv.lock /repo/backend/

# Extract version from package.json
WORKDIR /repo/frontend
RUN mkdir -p /version
RUN node -p "require('/repo/frontend/package.json').version" > /version/frontend.txt
RUN python -c "import tomllib; print(tomllib.load(open('/repo/backend/pyproject.toml', 'rb'))['project']['version'])" > /version/backend.txt

# relies on mounting this volume
WORKDIR /repo
USER root
ENTRYPOINT [ \
    "/bin/bash", "-c", \
    "./docker/entrypoints/entrypoint_fix_permissions.sh && \
     ./docker/entrypoints/entrypoint_user_scripts.sh && \
    su beetle -c ./docker/entrypoints/entrypoint_dev.sh" \
    ]


