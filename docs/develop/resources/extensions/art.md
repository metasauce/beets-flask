# Art extension

The art extension resolves cover art from external release URLs, such as
Spotify or MusicBrainz URLs. It is used by the `GET /art?url=<release-url>`
endpoint, which is currently used to get preview artwork for releases
in the web UI (before import).

The extension keeps service-specific artwork lookup outside the core. The core
only needs to provide a release URL and consume the resulting artwork, while
providers handle the details of talking to individual services.

## How it works

An art provider is responsible for two things:

1. Determining whether it supports a given release URL.
2. Resolving artwork for that URL.

When an art request is received, the extension finds a provider that supports
the URL and asks it to resolve the artwork. Providers use the HTTP session
provided by the extension, which takes care of common request configuration
such as timeouts and the `User-Agent`.

A provider can return either image data directly or URLs from which the
artwork can be fetched. The extension takes care of serving/proxying the resulting
image to the client.

## Adding a provider

Providers live in `beets_flask/extensions/providers/`. A provider should keep
all service-specific logic in its own module and expose only the functionality
required by the art extension.

For a first example, see
`beets_flask/extensions/providers/musicbrainz.py`. It demonstrates how a
provider extracts information from a release URL, communicates with an
external service, and returns artwork to the extension.

When implementing a provider, keep network operations asynchronous and use the
HTTP session supplied by the extension rather than creating a separate
session.
