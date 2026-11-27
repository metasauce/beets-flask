"""Foreign keys need an index.

SQLite does not create one for foreign key columns. Relationships are loaded
by these columns, so a missing index makes every load a full table scan.
"""

import pytest
from sqlalchemy import UniqueConstraint

from beets_flask.database.models.base import Base


def _foreign_key_columns():
    for table in Base.metadata.sorted_tables:
        for fk in table.foreign_keys:
            yield pytest.param(table, fk.parent, id=f"{table.name}.{fk.parent.name}")


@pytest.mark.parametrize("table, column", _foreign_key_columns())
def test_foreign_key_is_indexed(table, column):
    if column.primary_key:
        return

    # An index or unique constraint covers the column if it leads it
    leading = {next(iter(index.columns)).name for index in table.indexes} | {
        next(iter(constraint.columns)).name
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert column.name in leading
