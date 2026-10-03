from unittest import mock

from beets_flask.server.routes.musicbrainz import mb

MBID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class TestRequestReleasesByBarcode:
    def test_disabled_lookup_returns_none(self, monkeypatch):
        monkeypatch.setattr(mb, "_check_artists_enabled", lambda: False)
        assert mb._request_releases_by_barcode("1234") is None

    def test_parses_release_group_id(self, monkeypatch):
        payload = {
            "releases": [
                {
                    "id": "release-id-1",
                    "title": "The Album",
                    "score": "100",
                    "release-group": {"id": MBID},
                    "artist-credit": [{"name": "The Artist"}],
                }
            ]
        }
        response = mock.Mock()
        response.json.return_value = payload
        monkeypatch.setattr(mb, "_ws_url", lambda: "https://ws")
        monkeypatch.setattr(mb, "_rate_limit", lambda: None)
        monkeypatch.setattr(mb.requests, "get", lambda *a, **k: response)

        matches = mb._request_releases_by_barcode("0123456789012")
        assert matches == [
            {
                "mbid": MBID,
                "title": "The Album",
                "artist": "The Artist",
                "score": 100,
            }
        ]

    def test_query_uses_barcode_only(self, monkeypatch):
        captured = {}

        def fake_get(url, params, headers, timeout):
            captured["query"] = params["query"]
            response = mock.Mock()
            response.json.return_value = {"releases": []}
            return response

        monkeypatch.setattr(mb, "_ws_url", lambda: "https://ws")
        monkeypatch.setattr(mb, "_rate_limit", lambda: None)
        monkeypatch.setattr(mb.requests, "get", fake_get)

        mb._request_releases_by_barcode('0723540055629" OR')
        assert captured["query"] == 'barcode:"0723540055629 OR"'

    def test_falls_back_to_release_id_without_group(self, monkeypatch):
        payload = {
            "releases": [{"id": "release-id-1", "title": "A", "artist-credit": []}]
        }
        response = mock.Mock()
        response.json.return_value = payload
        monkeypatch.setattr(mb, "_ws_url", lambda: "https://ws")
        monkeypatch.setattr(mb, "_rate_limit", lambda: None)
        monkeypatch.setattr(mb.requests, "get", lambda *a, **k: response)

        matches = mb._request_releases_by_barcode("1234")
        assert matches[0]["mbid"] == "release-id-1"
        assert matches[0]["artist"] == ""

    def test_network_error_returns_none(self, monkeypatch):
        monkeypatch.setattr(mb, "_ws_url", lambda: "https://ws")
        monkeypatch.setattr(mb, "_rate_limit", lambda: None)
        monkeypatch.setattr(
            mb.requests, "get", mock.Mock(side_effect=mb.requests.RequestException())
        )
        assert mb._request_releases_by_barcode("1234") is None

    def test_bad_json_returns_none(self, monkeypatch):
        response = mock.Mock()
        response.json.side_effect = ValueError("bad json")
        monkeypatch.setattr(mb, "_ws_url", lambda: "https://ws")
        monkeypatch.setattr(mb, "_rate_limit", lambda: None)
        monkeypatch.setattr(mb.requests, "get", lambda *a, **k: response)
        assert mb._request_releases_by_barcode("1234") is None


class TestSearchReleaseByBarcode:
    def test_caches_by_barcode(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            mb, "_request_releases_by_barcode", lambda *a: calls.append(a) or []
        )
        monkeypatch.setattr(mb, "_cache", {})

        mb.search_release_by_barcode("1234")
        mb.search_release_by_barcode("1234")
        assert len(calls) == 1

    def test_different_barcode_is_different_cache_key(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            mb, "_request_releases_by_barcode", lambda *a: calls.append(a) or []
        )
        monkeypatch.setattr(mb, "_cache", {})

        mb.search_release_by_barcode("1234")
        mb.search_release_by_barcode("5678")
        assert len(calls) == 2

    def test_none_result_is_not_cached(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            mb, "_request_releases_by_barcode", lambda *a: calls.append(a) or None
        )
        monkeypatch.setattr(mb, "_cache", {})

        assert mb.search_release_by_barcode("1234") is None
        assert mb.search_release_by_barcode("1234") is None
        assert len(calls) == 2
