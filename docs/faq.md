# Frequently Asked Questions (FAQ)

## Archive support for 7z and rar files

Beets by default does not support 7z and rar files. However, you can enable support for these formats by installing the `unrar` and/or `py7zr` packages in your container. (See also [beets documentation](https://beets.readthedocs.io/en/stable/reference/cli.html#import)).

### `rar` support

To enable `rar` support, you can install the `unrar` package from the (non-free) Debian repositories.

```bash
# /config/startup.sh

# add `contrib non-free non-free-firmware` to components
sed -i '/Components:/s/main\b[^c]*$/main contrib non-free non-free-firmware/' \
    /etc/apt/sources.list.d/debian.sources

apt-get update
apt-get install -y unrar
```

```bash
# /config/requirements.txt
rarfile
```

### `7z` support

To enable `7z` support, you can use the `py7zr` package.

```bash
# /config/requirements.txt
py7zr
```

## Server hangs silently on older CPUs (no AVX2)

If logs show the server starting but the web UI never becomes reachable, your CPU may lack `AVX2`/`FMA`/`BMI1`/`BMI2` (common on Celeron/Pentium Silver N-series), which makes `polars` crash on import (`SIGILL`) silently in a background worker.

Fix: add polars' compatibility runtime and restart the container.

```bash
# /config/requirements.txt
polars[rtcompat]
```

```{note}
Reinstalled (~50 MB download) on every container *recreation* unless the uv cache is persisted. Not needed on newer hardware.
```

See #338.

## Troubleshooting and Debugging

A good starting point is to check the logs of the container. We can do this by running:

```bash
docker logs beets-flask
```

To get more detailed information, we can set environment variable of the container:

```yaml
services:
    beets-flask:
        environment:
            BEETSFLASKLOG: "/logs/beets-flask.log"
            LOG_LEVEL_BEETSFLASK: DEBUG
        volumes:
            - /path/to/logs/on/host:/logs
```

Which lets you increase the logs verbosity, and define where to put the logs.
