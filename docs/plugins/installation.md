# Installation

Installing beets plugins varies depending on the particular plugin. Make sure to always check the
[official docs](https://docs.beets.io/en/latest/plugins/index.html).

To install a plugin into the beets-flask container, place a `requirements.txt` and/or `startup.sh`
in either the `/config` folder or `/config/beets-flask` folder. The `requirements.txt` may include
[python dependencies](https://pip.pypa.io/en/stable/reference/requirements-file-format/), and the
`startup.sh` file may be an executable shell script compatible with the container's debian base.

On startup, the container runs as root the startup script if present, then installs requirements from
`requirements.txt` using [uv](https://docs.astral.sh/uv/pip/).

```{note}
We use uv to manage python dependencies in a virtual environment at `/repo/backend/.venv`.
This is activated by default (`which python`), but to install more dependencies you must
use `uv pip install` — a plain `pip install` will not place packages in the right location.
```

## Example: startup.sh (keyfinder)

The [keyfinder plugin](https://docs.beets.io/en/latest/plugins/keyfinder.html) requires manual
compilation of two C++ libraries. Place the following in a `startup.sh` file in either the
`/config` folder or `/config/beets-flask` folder.

```sh
#!/bin/sh

# get build dependencies
apt-get update
apt-get install -y \
    build-essential \
    ffmpeg \
    libavformat-dev \
    libavcodec-dev \
    libswresample-dev \
    libavutil-dev \
    git \
    cmake \
    libfftw3-dev \
    pkg-config \

# clone and build the library
git clone https://github.com/mixxxdj/libkeyfinder.git
cd libkeyfinder

cmake -DCMAKE_INSTALL_PREFIX=/usr/local -S . -B build
cmake --build build --parallel "$(nproc)"
cmake --install build

# clone and build the cli tool
cd ..
git clone https://github.com/evanpurkhiser/keyfinder-cli.git
cd keyfinder-cli/

cmake -DCMAKE_INSTALL_PREFIX=/usr/local -S . -B build
cmake --build build --parallel "$(nproc)"
cmake --install build
```

Make the script executable:

```sh
chmod +x ./startup.sh
```

Enable the plugin in your beets `config.yaml`:

```yaml
plugins:
    [
        keyfinder,
    ]

keyfinder:
    auto: yes
    bin: /usr/local/bin/keyfinder-cli
    overwrite: no
```

```{note}
To use another key format, create an alias of the executable and specify it in `config.yaml`.
Your container start-up time will increase considerably.
```

## Example: requirements.txt (discogs)

The [discogs plugin](https://docs.beets.io/en/latest/plugins/discogs.html) only needs a
Python dependency. Place the following in a `requirements.txt` file in the `/config` folder:

```
beets[discogs]
```

Then follow the [official docs](https://docs.beets.io/en/latest/plugins/discogs.html) to
configure the plugin in your `config.yaml`.
