# Beets library api

RESTful access to the beets music library with a JSON:API-ish subset for
discoverability, pagination, and relationships. Implemented in
`backend/beets_flask/server/routes/beets/` (items, albums), with the response
types defined in `beets/_types.py` and exported to the frontend via py2ts
(`backend/generate_types.py` -> `frontend/src/pythonTypes.ts`).

Base URL: `/api_v1/beets`
The global frontend fetch wrapper (`frontend/src/api/common.ts`) adds the
`/api_v1` prefix, so the SDK (`frontend/src/api/library.ts`) uses `/beets/...`.

## Error format

```json
{
  "errors": [{
    "status": "404",
    "title": "Not Found",
    "detail": "Item 123 not found"
  }]
}
```

## Endpoints

- `GET /items/<id>` - single item
- `PATCH /items/<id>` - update an item (attributes not given are left
  unchanged, `null` clears; `album_id`, `added`, `size`, `path`, `sources`
  are read-only and ignored)
- `DELETE /items/<id>?delete_file=true` - delete an item
- `GET /items/` - paginated item list (see below)
- `PATCH /items/` - bulk update, same filters as the list endpoint
- `DELETE /items/` - bulk delete, same filters

Albums mirror the item endpoints under `/albums/<id>` and `/albums/`, with
`DELETE` removing the album together with its items.

### GET (Paginated List)

```bash
GET /items
```

#### Query params

```bash
"filter_query"   # Beets query, e.g. filter_query=artist:"The Beatles"
"filter_ids"     # Explicit ids, repeatable: filter_ids=1&filter_ids=2
"sort"           # Single sort key, +/- prefix: sort=year / sort=-title
"limit"          # Results per page, default 100, max 1000
"cursor"         # Opaque cursor from links.next (hex-encoded JSON)
```

`filter_query` and `filter_ids` are combined with AND; without either, all
entities match. `sort` defaults to `-added`; allowed sortable fields are
`added, year, title, artist, albumartist, album, track, disc, length,
bitrate` for items and `added, year, album, albumartist, disctotal` for
albums. The cursor encodes the sort and the filters, so following pages only
need `cursor` (plus an optional `limit`); it cannot be combined with `sort`
or the filters.

#### Response

```jsonc
{
  "data": [{
    "type": "item",
    "id": "123",
    "attributes": { "title": "...", "artist": "...", "year": 1996, ... }
  }],
  "links": {
    "self": "/api_v1/beets/items/?sort=-added&limit=100",
    "next": "/api_v1/beets/items/?cursor=cD0yMDI0LTAx&limit=100"
  },
  "meta": { "total": 1 }
}
```

Item attributes: `title, artist, album, albumartist, album_id, year, month,
day, added, length, format, bitrate, samplerate, bitdepth, channels, label,
track, tracktotal, disc, disctotal, genres, isrc, catalognum, bpm, comment,
composer, initial_key, size, path, sources`. Empty values are omitted;
`title` is always present.

Album attributes: `title, albumartist, year, added, albumtype, genre,
genres, comp, label, catalognum, disctotal, gui_import_id, sources`. The
album's items are referenced in `data.relationships`; pass `include=items`
to embed them in full in the `included` section of the response.

### PATCH (Bulk Update)

```bash
PATCH /items?filter_query=artist:"The Beatles"
```

```jsonc
{
  "title": "Updated Title",    // Set
  "genre": null                // Clear
  // all not given are ignored
}
```

Responds with `{"meta": {"total": <number of updated entities>}}`.
Attributes are validated against the allowed attributes of the type;
read-only attributes (see above) are ignored.
