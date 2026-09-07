import logging
from typing import cast

from beets_flask.importer.session import AutoImportSession, BaseSession
from beets_flask.importer.stages import (
    StageOrder,
    identify_duplicates,
    match_threshold,
    user_query,
)

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


class DummySession(BaseSession):
    pass


def test_stage_insert_order():
    stages = StageOrder()

    # Workaround to avoid mypy error
    dummy_session: AutoImportSession = cast(AutoImportSession, None)

    stages.append(identify_duplicates(dummy_session))
    stages.append(user_query(dummy_session))
    stages.append(stage=user_query(dummy_session), name="foo")

    assert len(stages) == 3
    assert list(stages.keys())[0] == "identify_duplicates"
    assert list(stages.keys())[1] == "user_query"
    assert list(stages.keys())[2] == "foo"

    stages.insert(
        after="identify_duplicates", stage=match_threshold(dummy_session), name="bar"
    )

    assert len(stages) == 4
    assert list(stages.keys())[1] == "bar"

    stages.insert(
        before="identify_duplicates", stage=match_threshold(dummy_session), name="baz"
    )

    assert len(stages) == 5
    assert list(stages.keys())[0] == "baz"
