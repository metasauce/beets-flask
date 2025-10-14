# Installing beets plugins

```{warning}
We have not tested a lot of plugins with beets-flask gui.
Plugin support is experimental.
```

Installing beets plugins varies depending on the particular plugin.
[See the official docs](https://docs.beets.io/en/latest/plugins/index.html).

We might automate this in the future, but for now you can place a `requirements.txt` and/or `startup.sh` in either the `/config` folder or `/config/beets-flask` folder. The `requirements.txt` may include [python dependencies](https://pip.pypa.io/en/stable/reference/requirements-file-format/), and the `startup.sh` file may be an executable shell script that is compatible with the container's alpine linux base.

On startup, the container will run the startup script if it exists, and afterwards install the requirements from the `requirements.txt` file using pip.

## Example startup.sh: keyfinder

For example, we can install the [keyfinder plugin](https://docs.beets.io/en/latest/plugins/keyfinder.html) via `startup.sh`, as  it requires quite a few build steps.

Place the following in a `startup.sh` file in either the `/config` folder or `/config/beets-flask` folder.

```sh
#!/bin/sh

apt-get update
apt-get install -y \
    build-essential \
    ffmpeg \
    libkeyfinder-dev \
    git

git clone https://github.com/evanpurkhiser/keyfinder-cli.git
cd keyfinder-cli/
make
make install
```
Note that the container is based on alpine, so you have to use apk.
Make executable
```sh
chmod +x ./startup.sh
```


Edit beets `config.yaml` to include the plugin.
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

Note, in case you want to use another key format, you have to create an alias of the executable and specify that in the `config.yaml`.
Also, your container start-up time might increase considerably.


## Example requirements.txt: discogs

Place the following in a `requirements.txt` file in the `/config` folder.

```
beets[discogs]
```

and follow the instructions in the [official docs](https://docs.beets.io/en/latest/plugins/discogs.html).
