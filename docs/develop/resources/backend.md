# Backend 

Beets-Flask provides a quart application with REST API for the beets music library manager and a library for interacting with beets. 

```{toctree}
:hidden:

./state_serialize
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

## Database Migrations Guide

We use [Alembic](https://alembic.sqlalchemy.org/) for database migrations.

### Overview

- Migrations are stored in `backend/alembic/versions/`
- The database tracks its current version in the `alembic_version` table
- Migration files define `upgrade()` and `downgrade()` functions

### Quick Reference

| Task | Command |
|------|---------|
| Create migration | `alembic revision --autogenerate -m "description"` |
| Apply all pending | `alembic upgrade head` |
| Roll back one | `alembic downgrade -1` |
| Check version | `alembic current` |
| See history | `alembic history` |
| Validate | `alembic check` |

### Workflow: Creating a migration

We use a local database (`./beets-flask-sqlite.db`) to avoid breaking the docker setup.

1. Ensure you have a local database:
  ```bash
  cd backend
  alembic upgrade head
  ```

2. Edit the model (e.g., add a column to `states.py`)

3. Generate the migration:
  ```bash
  alembic revision --autogenerate -m "add_column_name"
  ```

4. Review the generated migration file in `alembic/versions/`

5. Apply the migration:
  ```bash
  alembic upgrade head
  ```

6. Validate with 
  ```bash
  alembic current  
  ```
