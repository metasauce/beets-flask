# Docker

We use docker for containerization and deployment of our application. You can find the files needed to build the docker images in the [`docker`](https://github.com/metasauce/beets-flask/tree/main/docker) folder.

Redis-Caching seems to be very persistent and we have not figured out how to completely reset it without _rebuilding_ the container.
Thus, currently, after code changes that run inside a redis worker `docker-compose up --build` is needed even when live-mounting the repo.

## Entrypoints

We use different entrypoints for the different environments. You can find all scripts in the [`docker/entrypoints`](https://github.com/metasauce/beets-flask/tree/main/docker/entrypoints) folder.
