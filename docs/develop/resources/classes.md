# Class Overview

To keep an overview which types come from beets native, we prefix them to `BeetsSomeType` (see `beets_flask/importer/types.py`)

## Notation

### Items

In Beets, an `Item` is a single track. The `Item` can be stored 
in the beets database. It represents a tracks metadata on disk.

### Candidates (TrackInfo & AlbumInfo)

Retrieved from external sources (e.g. spotify, tidal...). In particular `TrackInfo` is a single tracks metadata from an external source while `AlbumInfo` is information shared but also additional. `AlbumInfo` may contain a list of `TrackInfo`s.

### Matches (TrackMatch & AlbumMatch)

Matches are the association between `candidates` and `items`. Historically in beets this was just a list of indice mappings but changed to direct references to objects.

For the tracks of a candidate we may find the following relationships after trying
to assign items and tracks.

```
items ∩ tracks = pairs
items' ∩ tracks = extra_items
items ∩ tracks' = extra_tracks
```

Matches are ranked through predefined penalties and using linear assignment problem. This yields a percentage score.

### Task(s)

A `Task` is a specific import operation. Tasks need to be started on a folder i.e. `items` and looks up `candidates` online. The goal of task is to assign `items` to `candidates` by finding `matches`. A user can than pick a match. 

## Sessions and Queues

In Beets and BeetsFlask, folder imports are abstracted into sessions.
In BeetsFlask, each `Session` gets placed in a redis `Queue`, depending on its type:
Previews can take place in parallel, while imports take place one at a time, since this requires file movements on disk and writes into the beets database.

```{eval-rst}
.. mermaid:: ../../diagrams/sessions.mmd
```


## States

We keep states of various objects in our own database, mostly to be able to resume imports after generating the initial preview.
This requires us to wrap a lot of the beets objects, to make them persistable.

The state objects have a hierachy close to the beets internal logic:
- SessionState: Reflects the state of the import session.
- TaskState: Reflects an import task, but they dont have such a precise real-life meaning.
- CandidateState: Reflects a beets match (i.e. a candidate the user might choose)

```{eval-rst}
.. mermaid:: ../../diagrams/objects_state_relation.mmd
```

## PR279

```{eval-rst}
.. mermaid:: ../../diagrams/pr279.mmd
```
