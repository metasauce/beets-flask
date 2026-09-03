# Backend 

Beets-Flask provides a quart application with REST API for the beets music library manager and a library for interacting with beets. 

```{toctree}
:hidden:

./classes
./database
./state_serialize
./beets_library_api
```

## Resumability of import

By default beets has very limited support to resume an import after it has been triggered. For instance, once an import is canceled the next time the same folder is imported, beets will start from the beginning. This is not ideal for large imports, especially if you have a lot of plugins and candidate fetches may take a long time.

To overcome this issue we added wrappers for the beets sessions and introduced an serializable session state. This allows us to save the state of the import and resume it later, e.g. in a database. To see an example of this, please check the [state serialization example](./state_serialize).

## Environment variables

The configuration folders can be set via environment variables. This might be useful if you want to run the application in a different environment. The following values are our defaults for the production and dev docker containers:

```
BEETSDIR="/config/beets"
BEETSFLASKDIR="/config/beets-flask"
BEETSFLASKLOG="/logs/beets-flask.log"
```
