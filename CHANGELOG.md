# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - Upcoming

### ⚠️ Breaking Changes ⚠️

- **Base image changed**: The container base image is now `python:3.12-slim` (previously `python:3.11-alpine`). If you use a custom `startup.sh`, please verify compatibility, as Alpine-specific tooling and shell behavior may differ [#212](https://github.com/pSpitzner/beets-flask/issues/212)
- **Upgraded `beets` from `v2.5.1` to `v2.11.0`**
    - This contains many changes and improvements, including some plugins.
    - See the changelog at [beets.readthedocs.io](https://beets.readthedocs.io/en/stable/changelog.html)
- Changed config options (beets-flask):
    - `gui.inbox.folders.your_inbox.autotag` no longer accepts `false`, use `"off"` instead. (This was needed for consistency for the new config validation)
- Changed config options (beets):
    - `fetchart.sources` were changed, if you get errors from our previous defaults: change to `"*"`


### Added

- Config validation. When loading config files we now check that specified options will work. If not, the frontend will show an error message with details on what's wrong. This applies to `gui` settings (i.e. our own ones, `beets-flask/config.yaml`) and very select ones from native beets (only those which we use directly). Hopefully, this will eventually cover all config options of beets native, but this is more of an upsream task. [#224](https://github.com/pSpitzner/beets-flask/pull/224).
- Upload Files via the WebUI. You can now drag-and-drop single files into an inbox. To upload whole albums, zip them on your host first (uploading of folders directly is not implemented, as it would require a secure context).
- New config option `gui.terminal.enabled` (default: true) [#254](https://github.com/pSpitzner/beets-flask/pull/224)
- You can now alternatively use `PUID` and `PGID` instead of `GROUP_ID` and `USER_ID` environment variables. Good for [yaml anchors](https://docs.docker.com/reference/compose-file/fragments/). [#260](https://github.com/pSpitzner/beets-flask/issues/260)
- Use an external redis server by setting the `REDIS_URL` environment variable. [#277](https://github.com/pSpitzner/beets-flask/pull/277)

### Fixed

- Missing library stats dont cause a crash on first launch anymore [#264](https://github.com/pSpitzner/beets-flask/issues/264)
- Fixed a potential memory leak when checking if files are archives. We now only check the file extension instead of trying to open the file, which should avoid the issue with `tarfile.is_tarfile` [#258](https://github.com/pSpitzner/beets-flask/issues/258)
- Fixed tmux terminal could not start in some environments if `SHELL` was not set currently. We now always start a bash shell [#282](https://github.com/pSpitzner/beets-flask/issues/282)
- Container user `beetle` now uses bash terminal by default and activates the uv environment automatically.


### Other (dev)

- We now use `uv` to manage python dependencies and run scripts in CI/CD. This should improve dependency resolution and installation times.
- We now ship a static ffmpeg binary instead of installing ffmpeg via apt. This should reduce image size and improve compatibility across different host systems.
- Added a database migration setup using [Alembic](https://alembic.sqlalchemy.org/) for future database migrations.
- Removed unnecessary `nest_asyncio` dependency.
- Upgraded a number of frontend dependencies to their latest versions.

## [1.2.0] - 25-12-17

### ⚠️ Important ⚠️

- You need to update your beets config, and add `musicbrainz` to the list of enabled plugins. This is required because we updated the beets backend [see here](https://github.com/beetbox/beets/releases/tag/v2.4.0)

### Fixed

- Duration component could display nothing in some edge cases.
- Action buttons now have a slight box shadow and are a bit more visible.
- We now support playing container types [m4a, mp4, mov, alac, aac, mp3] that require seeking. This should fix issues with some mp4/m4a files not playing.
- If no candidates are found during an import, we now show a message instead of an empty screen. [#190](https://github.com/pSpitzner/beets-flask/issues/190)
- Archive files can now be deleted [#217](https://github.com/pSpitzner/beets-flask/issues/217)
- Import Bootleg Button now works as expected [#218](https://github.com/pSpitzner/beets-flask/issues/218)
- Startup script was not executed correctly if placed in `/config/beets-flask/startup.sh` [#227](https://github.com/pSpitzner/beets-flask/pull/227)
- Another state-related bug around Searching for Candidates [#225](https://github.com/pSpitzner/beets-flask/issues/225). We now no longer require a certaint type of state before allowing to add candidates.
- Asis candidates have been restyled to be more consistent with other candidate types. They now also include a cover art preview if available.
- Fixed a typo in our opiniated beets config [#235](https://github.com/pSpitzner/beets-flask/issues/235)
- Fixed a styling issue in the artists list view which caused an overflow
- Fixed a styling issue where an extra cancel-button (cross) was shown on webkit browsers

### Added

- Added ability to define more groups to take care of ACLs, so that our non-root user can delete files on host systems, if desired. New environment variable `EXTRA_GROUPS` [#234](https://github.com/pSpitzner/beets-flask/issues/234)
- The inbox info button now has a description of all actions [#145](https://github.com/pSpitzner/beets-flask/issues/145)
- Subpage for version information and configs. You can access it via the version number in the navbar. [#205](https://github.com/pSpitzner/beets-flask/issues/205)
- New config option `gui.inbox.debounce_before_autotag` to configure how many seconds to wait after the last filesystem event before starting autotagging. Same debounce applies to all inboxes. [#222](https://github.com/pSpitzner/beets-flask/issues/222)
- The library view on mobile now has a button to collapse the overview (above the tabs). This allows for more space when browsing the library on small screens.

### Other (dev)

- The default beets config now includes a `musicbrainz` section that enables fetching of external ids (like tidal).
- Fixed typing issues in `./tests` folder and enabled mypy check for it.
- Ruff now has the F401 (imported but unused) check enabled.
- Ruff now has the UP checks enabled to enforce modern python syntax.
- Unified coverart components in the frontend, we now use common styling for external and internal coverart.
- Moved inbox metadata fetching into the library api routes.
- Frontend formatter prettier is now enforced via a CI/CD workflow step

### Dependencies

- Updated `uvicorn` to `0.36.0`.
- Updated `beets` from `2.3.1` over [`2.4.0`](https://github.com/beetbox/beets/releases/tag/v2.4.0) to [`2.5.0`](https://github.com/beetbox/beets/releases/tag/v2.5.0). See the two changelogs!
- Updated a number of frontend dependencies, including `react-query`, `react-router`, `vite`, `typescript`, `eslint`, `prettier` and others. This partially required code changes due to breaking changes in these libraries. Should not affect normal usage tho.

## [1.1.3] - 25-09-18

### Added

- Docs now have a section on [limiations](https://beets-flask.readthedocs.io/latest/limitations.html)
- Pip `requirements.txt` and `startup.sh` can now be placed in `/config/` or `/config/beets-flask`, the latter is installed later.

### Fixed

- Resolved an issue in Vite development server where pythonTypes.ts would fail to load on first start due to inconsistent indentation (tabs vs spaces). This only affected the dev environment.
- Development Docker container now runs as the `beetle` user instead of root, improving parity with the production environment.
- Trailing slashes in configured inbox paths no longer cause crashes. [#182](https://github.com/pSpitzner/beets-flask/issues/182)
- The container now sets the `EDITOR` environment variable to `vi` so that `beet edit` and `beet config -e` work out of the box.

### Dependencies

- Updated `beets` to version `2.3.1`
- Updated `py2ts` to version `0.6.1`, now uses pypi distribution instead of github repo.

## [1.1.2] - 25-08-29

### Fixed

- Updated refresh_config to scan all modules for config references and overwrite them as needed to ensure consistency [#188](https://github.com/pSpitzner/beets-flask/issues/188)

## [1.1.1] - 25-08-15

### Fixed

- Session cache wasn't invalidated on all folder updates. This especially fixes an issues where the watchdog would not trigger a session invalidation when a folder was deleted or renamed. [#163](https://github.com/pSpitzner/beets-flask/issues/163)
- We now use the beets `ignore` config option to ignore files and folders in the inbox view. This allows you to ignore files like `*.tmp`, `*.log`, etc. We also allow users to define the `gui.inbox.ignore` option to customize the ignored file patterns. [#176](https://github.com/pSpitzner/beets-flask/issues/176)
- Scrollbar for beets instructions wasn't visible on small screens.

### Other (dev)

- Simplified translucent scroll setup in `__root.tsx`

### Added

- The items/track view now shows some basic information and you may play the track from there too.

## [1.1.0] - 25-07-29

### Added

- Support for importing archives `zip` and `tar` files. Support for `rar` and `7z` files can be added via custom startup and requirements files. See the [FAQ](https://beets-flask.readthedocs.io/latest/faq.html) for more information.

### Dependencies

- Updated `py2ts` to version `0.4.1`

## [1.0.3] - 25-07-29

### Fixed

- Fixed search results not showing [#161](https://github.com/pSpitzner/beets-flask/issues/161))
- Fixed search box not clickable on small screens [#162](https://github.com/pSpitzner/beets-flask/issues/162)

## [1.0.2] - 25-07-21

### Fixed

- Artists separators were not regex escaped correctly, leading to issues with artists containing special characters. Additionally an empty list of separators was not handled correctly. [#159](https://github.com/pSpitzner/beets-flask/issues/159)

## [1.0.1] - 25-07-17

### Added

- Configuration option for artist separator characters `gui.library.artist_separator`
- Docs subpage for configuration (including content)
- `typing_extensions` is now a dependency, to allow for more typing features
- The model api routes now allows for `DELETE` requests to delete resources by id. Not used yet but will be helpful for future features.

### Fixed

- Styling of candidate overview (major changes were not colored)
- For bootlegs, display of track changes after import no longer broken
- Navigating from inbox into folder details no longer toggles selection.
- Padding issue where navbar could block content on mobile.
- Cache invalidation now triggers on delete folder in frontend [#138](https://github.com/pSpitzner/beets-flask/issues/138)
- In albums and items view the clicking on artists does not return any results if the contained a separator character (e.g. `&`) [#132](https://github.com/pSpitzner/beets-flask/issues/138)
- Cleanup old actions.tsx file, which included old unused code [#134](https://github.com/pSpitzner/beets-flask/issues/134)
- The `cli_exit` event is now triggered after the import task is finished. This adds compatibility with some plugins which expected this event to be triggered after the import task is done. [#154](https://github.com/pSpitzner/beets-flask/issues/154).

### Changed

- Created `types.py` file to hold custom sqlalchemy types, and moved `IntDictType` there.

## [1.0.0] - 25-07-06

This is a breaking change, you will need to update your configs and delete your beets-flask
database (**not** the beets db!).

This marks a major milestone for beets-flask, as we now pretty happy with the current features
and the overall architecture.

### Changed

- Migrated backend to quart (the async version of flask)
- Reworked most of the frontend
- Removed interactive imports. We now store states for _any_ preview and import that is generated. Thus, sessions are resumable, and we can go back and forth seemlessly, to e.g. undo an import and pick a better candidate.
- Inbox types have changed. For now we only have `preview`, `auto` and `bootleg`.
- beets updated to version 2.2.0
- Implemented our own async pipeline for beets, that is typed and handles our custom sessions (should become obsolete once upstream PRs are merged).
- Improved library view, and track preview / streaming.
- Improved candidate preview, including cover art and asis details (current metadata).
- Terminal now has a bit of scroll-back and history.
- Much better test coverage.
- Now using [py2ts](https://github.com/semohr/py2ts) to automatically generate frontend (typescript) types from their backend (python) equivalents.
- New and improved logo.

## [0.1.1] - 25-06-08

Small version bump with fixes before jumping to 1.0.0.

### Added

- Option to install beets plugins by placing either `requirements.txt` or `startup.sh` in /`config`. cf. [Readthedocs](https://beets-flask.readthedocs.io/en/latest/plugins.html)
- [Documentation](https://beets-flask.readthedocs.io/en/latest/?badge=latest) on readthedocs.
- Option to import Asis via right-click, or as inbox type. Good for Bootlegs that do not
  have online meta data and you curate manually. Currently also applies `--group-albums`.

### Fixed

- Path escaping for right-click import via cli (#51)

## [0.1.0] - 24-11-13

### Fixed

- Renamed `kind` to `type` in search frontend code to be consistent with backend.
  Using kind for tags (preview, import, auto), and types for search (album, track).

### Changed

- Improved readme and onboarding experience
- Mountpoint to persist config files and databases changed to `/config` (was `/home/beetle/.config/beets/`)
  We create the `/config/beets` and `/config/beets-flask` folders on startup if they do not exist.
  Library files are placed there, and you can drop a `config.yaml` either or both of these folders. Settings in `/config/beets-flask/config.yaml` take precedence over `/config/beets/config.yaml`.
  **You will need to update your docker-compose!**

### Added

- Logo and favicon
- Image now on docker hub: `pspitzner/beets-flask:stable`
- Auto-import: automatically import folders that are added to the inbox if the match is good enough.
  After a preview, import will start if the match quality is above the configured.
  Enable via the config.yaml, set the `autotag` field of a configred inbox folders to `"auto"`.

## [0.0.4] - 24-10-04

### Fixed

- Config parsing should now work

### Added

- multi-disc albums are now supported
- Interactive import using a custom beets pipeline

### Changed

- Moved terminal to its own page, had to temporarily remove keyboard trigger
- Reworked the album folder detection algorithm, now uses more native beets code and is a bit faster
- Navbar styling and items overhaul

## [0.0.3] - 24-08-01

### Fixed

- default config: mandatory fields cannot be set in the yaml, or they
  might persist although the user sets them. moved to config loading in python.
- tmux session now restarts on page load if it is not alive.
- navbar, tags, inbox are now more friendly for mobile
- folder paths are now better escaped for terminal imports

### Added

- Backend to get cover art from metadata of music files.
- Impoved library view (mobile friendly, and a browser header component)
- Library search

### Changed

- Simplified folder structure of frontend
- Removed `include_paths` option from config and library backend (most of the frontend needs some form of file paths. thus, the option was not / could not be respected consistently)

## [0.0.2] - 24-07-16

### Fixed

- ESLint errors and Github action
- Now loading the default config

## 0.0.1 - 24-05-22

- initial commit

[Unreleased]: https://github.com/pSpitzner/beets-flask/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/pSpitzner/beets-flask/compare/v1.1.3...v1.2.0
[1.1.3]: https://github.com/pSpitzner/beets-flask/compare/v1.1.2...v1.1.3
[1.1.2]: https://github.com/pSpitzner/beets-flask/compare/v1.1.1...v1.1.2
[1.1.1]: https://github.com/pSpitzner/beets-flask/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/pSpitzner/beets-flask/compare/v1.0.3...v1.1.0
[1.0.3]: https://github.com/pSpitzner/beets-flask/compare/v1.0.2...v1.0.3
[1.0.2]: https://github.com/pSpitzner/beets-flask/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/pSpitzner/beets-flask/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/pSpitzner/beets-flask/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/pSpitzner/beets-flask/compare/v0.0.4...v0.1.0
[0.0.4]: https://github.com/pSpitzner/beets-flask/compare/v0.0.3...v0.0.4
[0.0.3]: https://github.com/pSpitzner/beets-flask/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/pSpitzner/beets-flask/compare/v0.0.1...v0.0.2
