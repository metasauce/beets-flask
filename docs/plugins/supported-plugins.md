# Compatibility

```{tip}
If a plugin works for you or doesn't, consider
[opening an issue or a PR](https://github.com/metasauce/beets-flask) to add it to the
compatible or incompatible list.
```

## Integrated

These plugins have explicit integration in beets-flask — dedicated icons,
art preview endpoints, or source links. Enabled in the default configuration.

### Spotify

The [spotify plugin](https://docs.beets.io/en/latest/plugins/spotify.html) has:

- Implements the {ref}`Art extension <art>`
- Dedicated Spotify SVG icon in the UI for source matches
- Art previews via the Spotify oEmbed API
- Links to open.spotify.com from the library view

Enabled by default.

### MusicBrainz

The [musicbrainz plugin](https://docs.beets.io/en/latest/plugins/musicbrainz.html) has:

- Implements the {ref}`Art extension <art>`
- Brain icon in the UI for MusicBrainz source matches
- Art previews via the Cover Art Archive
- Links to musicbrainz.org from the library view
- External ID mapping configured by default (discogs, bandcamp, spotify, deezer, beatport, tidal)

Enabled by default.

## Compatible

Plugins confirmed to work. No dedicated UI integration, but function correctly.

| Plugin                                                                    | Description                               |
| ------------------------------------------------------------------------- | ----------------------------------------- |
| [fetchart](https://docs.beets.io/en/latest/plugins/fetchart.html)         | Fetch album artwork from multiple sources |
| [embedart](https://docs.beets.io/en/latest/plugins/embedart.html)         | Embed fetched artwork into audio files    |
| [the](https://docs.beets.io/en/latest/plugins/the.html)                   | Move articles to end of names             |
| [ftintitle](https://docs.beets.io/en/latest/plugins/ftintitle.html)       | Move featured artists to title            |
| [lastgenre](https://docs.beets.io/en/latest/plugins/lastgenre.html)       | Fetch genres from Last.fm                 |
| [albumtypes](https://docs.beets.io/en/latest/plugins/albumtypes.html)     | Add album type info                       |
| [scrub](https://docs.beets.io/en/latest/plugins/scrub.html)               | Clean extraneous tags                     |
| [zero](https://docs.beets.io/en/latest/plugins/zero.html)                 | Null fields to reduce clutter             |
| [convert](https://docs.beets.io/en/latest/plugins/convert.html)           | Transcode audio files                     |
| [fromfilename](https://docs.beets.io/en/latest/plugins/fromfilename.html) | Guess metadata from filename              |
| [inline](https://docs.beets.io/en/latest/plugins/inline.html)             | Use Python snippets in templates          |
| [edit](https://docs.beets.io/en/latest/plugins/edit.html)                 | Edit metadata via external editor         |
| [discogs](https://docs.beets.io/en/latest/plugins/discogs.html)           | Match against Discogs                     |
| [keyfinder](https://docs.beets.io/en/latest/plugins/keyfinder.html)       | Detect musical key (requires compilation) |

## Incompatible

Plugins known to not work.

### chroma

The [chroma plugin](https://docs.beets.io/en/latest/plugins/chroma.html) generates
acoustic fingerprints to identify tracks without metadata. It is currently incompatible
with beets-flask due to a process boundary issue.

Beets runs the entire import pipeline (tagging → importing) in a single process,
which allows the chroma plugin to store fingerprint data in global memory across both
phases. Beets-flask splits tagging and importing into separate, potentially different
processes. The chroma plugin's in-memory state does not survive this boundary, so
fingerprint data collected during tagging is lost before the import phase can write
it to disk.

This is a design limitation in the plugin itself, it would need to be refactored
to use persistent storage (e.g. writing directly to files during tagging) to work
in a multi-process environment.

(extensions)=

## Extensions

Beets-flask uses extensions to provide additional functionality. The sections
below describe the available extensions and how they are used. The plugin
documentation above indicates which extensions are used by each plugin.

All extensions are built on beets-flask's
[extension system](../develop/resources/extensions.md).

(art)=

### Art

The Art extension provides cover artwork for external release URLs. It allows
beets-flask to show artwork previews for releases before they are imported.
