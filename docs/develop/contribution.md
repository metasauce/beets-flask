# Contributing

We are always happy to see new contributors! If small or large, every contribution is welcome. Please follow these guidelines to ensure a smooth contribution process.

## Prerequisites

Some technical knowledge for the following tools is required to get started with the project. If you are not familiar with them, please check out the documentation for each tool and make sure you have them installed.

-   [Docker](https://docs.docker.com/get-started/)
-   [Docker Compose](https://docs.docker.com/compose/)
-   [Python](https://www.python.org/downloads/) 3.10 or higher
-   [Node.js](https://nodejs.org/en/download/) 18 or higher
-   [git](https://git-scm.com/downloads)
-   [pnpm](https://pnpm.io/installation) (or any other package manager)

## Setting Up the Development Environment

1. **Clone the repository:**

```bash
git clone https://github.com/pSpitzner/beets-flask
cd beets-flask
```

2.1 **Install the dependencies (backend):**
We recommend using uv to manage the python dependencies but you can also use pip and a virtual environment of your choice.

```bash
cd backend
uv sync --all-extras --dev
source .venv/bin/activate
# or
pip install -e .[dev]
```

2.2 **Install the dependencies (frontend):**
We use [pnpm](https://pnpm.io/) to manage the frontend dependencies. You may use any other package manager. On macOS you might want to run this command inside the container ([see here](resources/macos)).

```bash
cd frontend
pnpm install --frozen-lockfile
```

3. **Run the application in dev mode:**
   Check the docker compose file and edit if necessary.

```bash
cd ../
# We recommend to create a copy of the docker compose file
cp ./docker/docker-compose.dev.yaml ./docker/docker-compose.dev-local.yaml
# Run the application after editing the docker compose file
docker compose -f ./docker/docker-compose.dev-local.yaml up --build
```

## Install pre-commit hooks

We automatically check for code style and formatting issues using pre-commit hooks. To install the hooks, run the following command (optional):

```bash
pip install pre-commit
pre-commit install
```

## Before Submitting a Pull Request

Run [Ruff](https://docs.astral.sh/ruff/) manually or use the pre-commit hooks to check for any issues. Additionally, run the tests to ensure that your changes do not break any existing functionality.

```bash
cd backend
# Code formatting and linting
ruff check
ruff lint
# Typing checks
mypy .
# Run the tests
pytest
```

Run [eslint](https://eslint.org/) manually or use the pre-commit hooks to check for any issues. Additionally, run the tests to ensure that your changes do not break any existing functionality.

```bash
cd frontend
# Run eslint manually
pnpm lint
# Check the types
pnpm check-types
```

## Submitting a Pull Request

Fork the repository and create a new branch for your changes. Feel free to follow [this guide](https://docs.github.com/en/get-started/quickstart/contributing-to-projects) for more information on how to create a pull request. Once you are done we will review your changes as soon as possible. Please be patient, as we are a small team and may not be able to review your changes immediately.

## Example docker compose

```bash
git clone https://github.com/pSpitzner/beets-flask.git ./beets_flask_dev
cd ./beets_flask_dev
mkdir local
```

Tweak `docker/docker-compose.dev.yaml` to your needs. Important is to live mount your repo folder:

```yaml
services:
    beets-flask:
        container_name: beets-flask
        hostname: beets-container
        build:
            context: ..
            dockerfile: docker/Dockerfile
            target: dev
        image: beets-flask
        restart: unless-stopped
        ports:
            - "5001:5001"
            - "5173:5173"
        environment:
            USER_ID: 1000
            GROUP_ID: 1000
            LOG_LEVEL_BEETSFLASK: DEBUG
            LOG_LEVEL_OTHERS: WARNING
        volumes:
            - ../local/music/:/music/
            - ../local/config/:/config
            - ../:/repo/
```

After first launch you will need to install the frontend packages:

```bash
docker exec -it -u beetle beets-flask-dev bash
cd /repo/frontend
pnpm i
```

Check the viteserver at `localhost:5173`
