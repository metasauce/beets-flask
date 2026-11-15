# Getting started

We provide a docker image with the full beeets-flask setup. You can run it with docker-compose or docker. We recommend using the `stable` tag, alternatively you may use `latest` for the most recent build.

## Using docker compose

Follow these steps to quickly set up and run the Beets-Flask application using Docker.

1. Create a new directory:

```bash
mkdir beets-flask
cd beets-flask
```

2. Download the `docker-compose.yaml` file or create it manually and copy the content from below.

```bash
wget https://raw.githubusercontent.com/metasauce/beets-flask/main/docker/docker-compose.yaml
```

If you want to create it manually, you can use the following content:

```{literalinclude} ../docker/docker-compose.yaml
:language: yaml
```

3. Edit the docker-compose.yaml file! Please change the configuration and volume paths, otherwise the application might not start or work correctly. See the [configuration](configuration_sec) section for more information.

4. Start the application using docker-compose.

```bash
docker-compose up
```

The application should now be available at `http://localhost:5001`!

## Using docker

Similarly, you can also run the application using docker directly. Feel free to adjust the following command to your needs.

```{include} ../README.md
:start-after: <!-- start setup container -->
:end-before: <!-- end setup container -->
```

(configuration_sec)=

## Configuration

As the minimum, you need to update the information about your music folders. Edit `config/beets/config.yaml` to point to your music library: The config mount has to point to the same folders inside and outside the container!

```yaml
# config/beets/config.yaml
# Update to your mounted music folder!
directory: /music_path/clean/
```

Please checkout the [configuration](configuration.md) page for more customization options and further
details about the configuration files.

### Use your existing beets library

**Make a backup!** Your config folder `~/.config/beets/` should be the minimum.

Mount your existing beets config folder to the container. This way you can use your existing beets library and configuration.

```yaml
# docker-compose.yml
volumes:
    - ~/.config/beets/:/config/beets/
    - ~/.config/beets-flask/:/config/beets-flask/
    - /music_path/clean/:/music_path/clean/
```

Make sure that the `library` location in your beets `config.yaml` is either set to the path _inside_ the container, or not specified (the default should work).

```{note}
The `/music_path/clean/` needs to be consistent inside and outside of the container. Otherwise beets will not be able to manage files correctly. For instance if your music is in `/home/user/music/`, you should mount with `/home/user/music/:/home/user/music/`.
```

```{warning}
You might get mixed results if your beets library comes from a newer version than we ship with beets-flask. Beets currently does not handle library downgrades. **Make a backup first!**
```

### To start from scratch or with a copy of your existing library

In your docker compose, mount a fresh config folder

```yaml
# docker-compose.yml
volumes:
    - /music_path/config/:/config/
    - /music_path/inbox/:/music_path/inbox/
    - /music_path/imported/:/music_path/imported/
```

Start the container, and you will find some files placed in the mounted config folder. Then either start customizing a config here, or copy content from your `~/.config/beets/` to `/music_path/config/beets/`
