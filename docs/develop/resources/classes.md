# Class Overview

## Sessions and Queues

In Beetsflask, folder imports are abstracted into sessions.
Each `Session` gets placed in a redis `Queue`, depending on its type:
Previews can take place in parallel, while imports take place one at a time, since this requires file movements on disk and writes into the beets database.

```{eval-rst}
.. mermaid:: ../../diagrams/sessions.mmd
```


## States

We keep states of various objects in our own database, mostly to be able to resume imports after generating the initial preview.
This requires us to wrap a lot of the beets objects, to make them persistable.

The state objects have a hierachy close to the beets internal logic:
- SessionState: Reflects the state of the import session.
- TaskState: Reflects a beetstask, but they dont have such a precise real-life meaning.
- CandidateState: Reflects a beets match (i.e. a candidate the user might choose)

```{eval-rst}
.. mermaid:: ../../diagrams/objects_state_relation.mmd
```
