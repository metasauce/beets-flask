# Auth extension

The auth extension provides authentication with external services for beets
plugins that need it. Some plugins only work after the user has authenticated
with a service (e.g. Tidal), which normally means running a command like
`beet tidal --auth` on the command line. The auth extension exposes the same
flow through the `/auth` API endpoints, so authentication can happen in the
browser from the beets-flask web UI.

## How it works

Authentication uses the PKCE flow (RFC 7636): the user authenticates in their
browser, and the resulting authorization code is exchanged for a token. A
provider implements two steps:

1. `start_authentication()` returns the URL the user must visit, together with
   sensitive flow state (the PKCE code verifier and CSRF state).
2. After the user logs in, the service redirects back with an authorization
   code. The caller passes the redirect URL (plus the flow state) to
   `complete_authentication()`, which exchanges the code for a token and
   persists it.

The extension itself does not persist any state: the caller keeps the flow
state server-side between the two steps and hands the client only an opaque
`flow_id`. The provider is responsible for persisting the token once the flow
is complete.

## Adding a provider

Providers live in `beets_flask/extensions/providers/`. A provider subclasses
`AuthExtension` and implements `name`, `is_enabled()`, `is_authenticated()`,
`start_authentication()` and `complete_authentication()`, then registers in
the `AUTH_EXTENSIONS` list in `beets_flask/extensions/providers/__init__.py`.

For a first example, see
`beets_flask/extensions/providers/tidal.py`. It reuses the OAuth session of
beets' tidal plugin to generate the authorization URL and exchange the code,
and the plugin itself saves the resulting token.

The flow state is sensitive and single-use: the code verifier must never reach
the client, and a consumed or expired `flow_id` cannot be replayed to complete
a flow.
