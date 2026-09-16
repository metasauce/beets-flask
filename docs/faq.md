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
