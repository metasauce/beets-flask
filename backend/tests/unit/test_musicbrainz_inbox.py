from types import SimpleNamespace

from beets_flask.server.routes.musicbrainz.resources import _session_summary

MBID_A = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

FOLDER = SimpleNamespace(
    full_path="/music/inbox/Antidote",
    hash="abc123",
    type="directory",
    is_album=True,
)


def _match(data_url: str) -> SimpleNamespace:
    return SimpleNamespace(info=SimpleNamespace(data_url=data_url))


def _best(distance: float, data_url: str) -> SimpleNamespace:
    return SimpleNamespace(
        distance=SimpleNamespace(distance=distance),
        match=_match(data_url),
        album="Best Album",
        artist="Best Artist",
    )


def _task(metadata=None, best=None) -> SimpleNamespace:
    return SimpleNamespace(
        current_metadata=metadata or {},
        best_candidate_state=best,
    )


class TestSessionSummary:
    def test_no_session(self):
        """Albums without a session have no match info."""
        summary = _session_summary(FOLDER, None)

        assert summary == {
            "folder_path": FOLDER.full_path,
            "folder_hash": FOLDER.hash,
            "type": "directory",
            "name": None,
            "albumartist": None,
            "year": None,
            "match_percentage": None,
            "match_mbid": None,
            "has_session": False,
            "has_match": False,
        }

    def test_session_without_candidates(self):
        """A session without candidates shows the current metadata only."""
        task = _task(
            metadata={"album": "Antidote", "albumartist": "Milk", "year": "1996"}
        )
        summary = _session_summary(FOLDER, task)

        assert summary["has_session"] is True
        assert summary["has_match"] is False
        assert summary["name"] == "Antidote"
        assert summary["albumartist"] == "Milk"
        assert summary["year"] == "1996"
        assert summary["match_percentage"] is None
        assert summary["match_mbid"] is None

    def test_session_with_match(self):
        """The best candidate provides the match percentage and MBID."""
        task = _task(
            metadata={"album": "Antidote", "year": "1996"},
            best=_best(0.0889, f"https://musicbrainz.org/release/{MBID_A}"),
        )
        summary = _session_summary(FOLDER, task)

        assert summary["has_match"] is True
        assert summary["match_percentage"] == 91.1
        assert summary["match_mbid"] == MBID_A
        assert summary["name"] == "Antidote"

    def test_match_fills_missing_metadata(self):
        """The best candidate fills missing album/artist names."""
        task = _task(
            metadata={},
            best=_best(0.05, f"https://musicbrainz.org/release/{MBID_A}"),
        )
        summary = _session_summary(FOLDER, task)

        assert summary["name"] == "Best Album"
        assert summary["albumartist"] == "Best Artist"

    def test_match_without_mbid_url(self):
        """A candidate without a release url has no MBID."""
        task = _task(metadata={}, best=_best(0.05, "https://example.com/foo"))
        summary = _session_summary(FOLDER, task)

        assert summary["has_match"] is True
        assert summary["match_mbid"] is None
