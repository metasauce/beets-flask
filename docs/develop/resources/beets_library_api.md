# Beets library api

Our API provides RESTful access to the beets music library with JSON:API conventions for discoverability, pagination, and relationships. It supports:

- Beets DB operations: Query/update/delete Items synced with filesystem metadata.
- Independent file metadata: Read/write tags on files without beets Item (auto-creates/syncs Item if path exists in DB).
- Beets-native queries: Full beets query language support.

To isolate the library layer we opted to expose all endpoints after the base

Base URL: `/api/v1/beets`
Content-Type: `application/vnd.api+json`

## Error format

{
  "errors": [{
    "status": "404",
    "title": "Not Found",
    "detail": "Item 123 not found"
  }]
}

## Endpoints

### GET Items (Paginated List)

```bash
GET /items
```

#### Query params

```bash
"filter[query]"  # Beets query query=artist:"The Beatles"
"filter[ids]"    # Beets ids for filtering
"sort"   # Comma fields (+/- asc/desc)	sort=year,-title
"limit"	 # Results per page limit=50
"cursor" # Opaque cursor (base64) cursor=cD0yMDI0LTAx
```
Only one of query and ids can be given.
Cursor decodes to (sort_key, last_value, direction).

#### Response

```jsonc
{
  "data": [{"type": "items", "id": "123", "attributes": {"title": "..."}}],
  "links": {
    "self": "/items?query=...&cursor=...",
    "next": "/items?query=...&cursor=cD0yMDI0LTAx",  // Next cursor
    "prev": "/items?query=...&cursor=YWRkOmZpcnN0"   // Prev cursor
  },
  "meta": {
    "total": 1
  }
}
```

### PATCH Items (Bulk Update)

Purpose: Bulk update matching items (query) or specific IDs. Supports same filters and
returns same response as GET for consistency.

```bash
PATCH /items
```

#### Query params

```bash
"filter[query]"  # Beets query to filter items
"filter[ids]"    # Beets ids for filtering
# Only relevant for response
"sort"   # Comma fields (+/- asc/desc)	sort=year,-title
"limit"	 # Results per page limit=50
```

#### Request body

```jsonc
{
  "data": {
    "type": "items",
    "attributes": {
      "title": "Updated Title",    // Set
      "genre": null                // Clear
      // all not given are ignored
    }
  }
}
```

Attributes should be validated against allowed attributes.

### Response

Same as get request. Allows to retrieve updated data.
