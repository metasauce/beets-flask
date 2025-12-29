# Configuration

On first container launch, config files are automatically generated in the mounted `/config` folder.
Configurations are read from:

-   `config/beets/config.yaml` (for the original cli tool that we wrap)
-   `config/beets-flask/config.yaml` (for frontend and container settings)

```{warning}
Configuration changes are only applied on container restart.
Restart your container with `docker restart beets-flask` after changing a configuration option.
```

We extend the [default beets configuration](https://beets.readthedocs.io/en/stable/reference/config.html) with some additional options.
You may use the following example configuration as a starting point.
It contains all options that can be set in the `/config/beets-flask/config.yaml`.

```{literalinclude} ../backend/beets_flask/config/config_bf_example.yaml
:language: yaml
```

## Inboxes

Allows you to configure the inboxes that are used to automatically import music files into your library.
You may add multiple inboxes, each may have a different purpose.

### `gui.inbox.folders`

The `gui.inbox.folders` section allows you to define multiple inboxes, each with a name, path, and an `autotag` setting.
The `autotag` setting determines how the files in the inbox are processed by beets-flask.

-   <i data-lucide="inbox"></i> `"off"` you have to do everything manually.
-   <i data-lucide="tag"></i> `"preview"` fetch meta data from online sources, but don't import yet.
-   <i data-lucide="rocket"></i> `"auto"` fetch meta data, and import if the match is good enough (based on threshold).
-   <svg class="icon" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-sneaker-icon lucide-sneaker"><path d="M14.1 7.9 12.5 10"/><path d="M17.4 10.1 16 12"/><path d="M2 16a2 2 0 0 0 2 2h13c2.8 0 5-2.2 5-5a2 2 0 0 0-2-2c-.8 0-1.6-.2-2.2-.7l-6.2-4.2c-.4-.3-.9-.2-1.3.1 0 0-.6.8-1.2 1.1a3.5 3.5 0 0 1-4.2.1C4.4 7 3.7 6.3 3.7 6.3A.92.92 0 0 0 2 7Z"/><path d="M2 11c0 1.7 1.3 3 3 3h7"/></svg> `"bootleg"` you are sure the meta data is fine, or it does not exist online.
    Drop files to import as-is in here, _but still create one subfolder for each
    import session you want to create_. (Beets acts on _folders_.
    Files directly inside the inbox wont trigger an imported)

Note that the top label (i.e. Inbox1, Inbox2...) does not matter.

```yaml
gui:
    inbox:
        folders:
            Inbox1:
                name: "Dummy inbox"
                path: "/music/dummy"
                autotag: "off"
                # do not automatically trigger tagging and do not automatically import

            Inbox2:
                name: "An Inbox that only generates the previews"
                path: "/music/inbox_preview"
                autotag: "preview"
                # trigger tag but do not import, recommended for most control

            Inbox3:
                name: "Auto Inbox"
                path: "/music/inbox_auto"
                autotag: "auto"
                # trigger tag and import if a good match is found based on `auto_threshold`

                auto_threshold: null
                # if set to null, uses the value in beets config (match.strong_rec_thresh)
                # define the distance from a perfect match, i.e. set to 0.1 to import
                # matches with 90% similarity or better.

            Inbox4:
                name: "Paul's Bootlegs"
                path: "/music/inbox_bootlegs"
                autotag: "bootleg"
                # Import as-is using the meta data of files, and group albums
                # using the metadata, even if they are in the same folder
                # Effectively `beet import ... --group-albums -A`
```

---

### `gui.inbox.debounce_before_autotag`

Specify the number of seconds to wait after the last filesystem event before starting the autotagging process.
Applies to _all_ inboxes.
For example, when adding files one by one, the timer gets reset after each file.
Tagging only starts after no new files have been added for the specified time.
Increase this to avoid integrity warnings when files are added slowly.
The default value is `30` seconds.

---

### `gui.inbox.ignore`

Specifies a list of file patterns to ignore when scanning the inbox folders.
This is useful to exclude temporary files or other unwanted files from being shown in the inbox.

If not set, this will default to the [`ignore`](https://docs.beets.io/en/stable/reference/config.html#ignore) config from the `beets/config.yaml` file.

To show all files in the inbox (independent of which files beets will copy) set this to an empty list `[]`.

```yaml
# beets-flask/config.yaml
gui:
    inbox:
        ignore:
            # Usually you want to keep these in place.
            # When customizing, we _do not_ copy beets defaults over.
            - ".*"
            - "*~"
            - "System Volume Information"
            - "lost+found"
            # also exclude some common resource files on Synology NAS
            - "@eaDir"
            - "@SynoEAStream"

# default in beets config
ignore:
    - ".*"
    - "*~"
    - "System Volume Information"
    - "lost+found"
```

## Library

The `gui.library` section contains options for the library view in the web interface.
It allows you to configure how the library is displayed and how we interact with the beets library.

### `gui.library.artist_separators`

A list of characters that are used to split artist names in the library view.
This is mainly used to handle artist searches and filtering.
If you don't want this feature, you can set it to an empty list `[]`.
The default is `[";", ",", "&"]`.

## Terminal

### `gui.terminal.start_path`

Specifies the path that is used when starting the terminal in the web interface.
This is useful if you want to start the terminal in a specific directory, such as your music library.
The default value is `/music/inbox`.
You should change this if you have a different inbox path!

## Other options

### `gui.num_preview_workers`

Specifies the number of worker threads that are used to generate previews for the inboxes.
This is useful to speed up the preview generation process, especially when you have a large number of items in your inboxes.
The default value is `4`.

```{note}
You can use multiple workers to fetch candidates before importing (previewing).
However, the import itself is always done sequentially.
This is to ensure that the import process is not interrupted by other operations.
```

### `gui.inbox.temp_dir` 
Specifies the temporary directory that is used to store files during the upload process. 
This is useful to ensure that files are uploaded to a filesystem that is fast and has enough
space. The default value is `/tmp/beets-flask/upload`.

## Docker Environment Variables

These environment variables are set in the `docker-compose.yaml` file and control the container's behavior.

### `USER_ID` and `GROUP_ID`

The `USER_ID` and `GROUP_ID` environment variables are used to set the UID and GID of the `beetle` user inside the container. This is useful to match the user and group IDs of the host system. The default value is `1000` for both.

```yaml
environment:
    USER_ID: 1000
    GROUP_ID: 1000
```

### `EXTRA_GROUPS`

The `EXTRA_GROUPS` environment variable allows you to add additional groups to the `beetle` user. This is useful when you need the container to have access to files owned by different groups on the host system.

The format is a comma-separated list of `group_name:gid` pairs:

```yaml
environment:
    EXTRA_GROUPS: "nas_shares:1001,media:1002"
```

This is particularly useful in scenarios where:

-   Files in the inbox are created by external services running as different users/groups
-   You're using ACL-based permissions with specific group access
-   You're running in environments like LXC/Proxmox with mapped group IDs
-   You need the container to manage files from network shares with specific group ownership

Example: If your download client (e.g., slskd, transmission) creates files with group ownership `nas_shares` (gid 1001), you can add that group to the beetle user:

```yaml
environment:
    EXTRA_GROUPS: "nas_shares:1001"
```

This will allow the beets-flask container to delete and manage those files via the web UI.

## Validation

Beets Flask validates it's own configuration[^1] and a few select fields of the native beets configs. The frontend and docker log messages will inform you of any typos or incompatible values.

[^1]: Powered by [eyconf](https://github.com/semohr/eyconf)

```{figure} _static/config_error.webp
Note however, for these changes to take full effect in beets-flask's background workers, you still need to manually restart the container (despite that cheeky _retry_ button)!
```
