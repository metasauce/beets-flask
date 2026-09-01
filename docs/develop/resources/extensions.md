# Extensions

Beets-flask uses a small extension system to add optional functionality
without coupling the core to any particular service. Extensions wrap external
services (e.g. Spotify, MusicBrainz) behind a common interface, so the core
can consume optional services without knowing their implementation details.

## How it works

- **Extension type** — a capability the core knows how to consume. Each type
  lives in its own module under `beets_flask/extensions/` and defines an
  abstract base class (the interface) plus any result types it needs.
- **Provider** — a concrete implementation of an extension type for one
  specific service. Providers live in `beets_flask/extensions/providers/`,
  one module per provider.
- **Registry** — the list of providers the core consults. Currently a simple
  hard-coded list per extension type (`ART_SOURCES` for art); adding a
  provider means one registration line in
  `beets_flask/extensions/providers/__init__.py`.

Consumers in the core (routes, workers) ask each provider in the registry
whether it handles the given input, then call it to do the work, the core
never knows which provider handled a request.

## Extension types

Functionality is split into separate extension types to keep the system
modular and make individual capabilities easy to extend.

```{toctree}
:maxdepth: 1

extensions/art.md
extensions/auth.md
```
