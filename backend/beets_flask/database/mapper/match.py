from beets_flask.importer.types import (
    BeetsAlbumInfo,
    BeetsAlbumMatch,
    BeetsDistance,
    BeetsItem,
    BeetsTrackInfo,
    BeetsTrackMatch,
)

from ..models.match import (
    AlbumInfo,
    AlbumMatch,
    AlbumMatchTrackMapping,
    Distance,
    Match,
    Penalty,
    TrackInfo,
    TrackMatch,
)
from .base import BeetsMapper, Context

# ----------------------------------- Info ----------------------------------- #


class TrackInfoMapper(BeetsMapper[BeetsTrackInfo, TrackInfo]):
    def _from_beets(self, obj: BeetsTrackInfo, ctx: Context) -> TrackInfo:
        data = {k: v for k, v in obj.items() if not k.startswith("_")}
        model = TrackInfo(data=data)
        return model

    def _to_beets(self, model: TrackInfo, ctx: Context) -> BeetsTrackInfo:
        beets_obj = BeetsTrackInfo(**model.data)
        return beets_obj


class AlbumInfoMapper(BeetsMapper[BeetsAlbumInfo, AlbumInfo]):
    def __init__(self):
        self.track_mapper = TrackInfoMapper()

    def _from_beets(self, obj: BeetsAlbumInfo, ctx: Context) -> AlbumInfo:
        data = {k: v for k, v in obj.items()}
        data.pop("tracks", None)
        return AlbumInfo(
            tracks=[self.track_mapper.from_beets(t, ctx) for t in obj.tracks],
            data=data,
        )

    def _to_beets(self, model: AlbumInfo, ctx: Context) -> BeetsAlbumInfo:
        data = dict(model.data)
        data.pop("tracks", None)
        return BeetsAlbumInfo(
            tracks=[self.track_mapper.to_beets(t, ctx) for t in model.tracks],
            **data,
        )


class DistanceMapper(BeetsMapper[BeetsDistance, Distance]):
    def __init__(self):
        self.track_mapper = TrackInfoMapper()

    def _from_beets(self, obj: BeetsDistance, ctx: Context) -> Distance:
        penalties = [Penalty(key=k, value=v) for k, v in obj._penalties.items()]

        track_distances: list[Distance] = []
        for beets_track_info, track_distance in obj.tracks.items():
            child = self.from_beets(track_distance, ctx)
            child.track_info = self.track_mapper.from_beets(beets_track_info, ctx)
            track_distances.append(child)

        return Distance(
            raw_distance=obj.raw_distance,
            max_distance=obj.max_distance,
            penalties=penalties,
            track_distances=track_distances,
        )

    def _to_beets(self, model: Distance, ctx: Context) -> BeetsDistance:
        distance = BeetsDistance()

        for penalty in model.penalties:
            for value in penalty.value:
                distance.add(penalty.key, value)

        for track_distance in model.track_distances:
            if track_distance.track_info is not None:
                distance.tracks[
                    self.track_mapper.to_beets(track_distance.track_info, ctx)
                ] = self.to_beets(track_distance, ctx)

        return distance


# ---------------------------------- Matches --------------------------------- #


class TrackMatchMapper(BeetsMapper[BeetsTrackMatch, TrackMatch]):
    def __init__(self):
        self.track_info_mapper = TrackInfoMapper()
        self.distance_mapper = DistanceMapper()

    def _from_beets(self, obj: BeetsTrackMatch, ctx: Context) -> TrackMatch:
        return TrackMatch(
            info=self.track_info_mapper.from_beets(obj.info, ctx),
            distance=self.distance_mapper.from_beets(obj.distance, ctx),
        )

    def _to_beets(self, model: TrackMatch, ctx: Context) -> BeetsTrackMatch:
        return BeetsTrackMatch(
            info=self.track_info_mapper.to_beets(model.info, ctx),
            distance=self.distance_mapper.to_beets(model.distance, ctx),
        )


class AlbumMatchMapper(BeetsMapper[BeetsAlbumMatch, AlbumMatch]):
    def __init__(self):
        self.album_info_mapper = AlbumInfoMapper()
        self.distance_mapper = DistanceMapper()
        self.track_info_mapper = TrackInfoMapper()

    def _from_beets(self, obj: BeetsAlbumMatch, ctx: Context) -> AlbumMatch:
        model = AlbumMatch(
            info=self.album_info_mapper.from_beets(obj.info, ctx),
            distance=self.distance_mapper.from_beets(obj.distance, ctx),
        )

        # extra tracks
        for extra_track in obj.extra_tracks:
            model.track_mappings.append(
                AlbumMatchTrackMapping(
                    track_info=self.track_info_mapper.from_beets(extra_track, ctx),
                    item=None,
                )
            )

        # extra items
        for extra_item in obj.extra_items:
            model.track_mappings.append(
                AlbumMatchTrackMapping(
                    track_info=None,
                    item=extra_item,
                )
            )

        # mappings
        for item, track in obj.mapping.items():
            model.track_mappings.append(
                AlbumMatchTrackMapping(
                    track_info=self.track_info_mapper.from_beets(track, ctx),
                    item=item,
                )
            )

        return model

    def _to_beets(self, model: AlbumMatch, ctx: Context) -> BeetsAlbumMatch:
        mapping: dict[BeetsItem, BeetsTrackInfo] = {}
        extra_items: list[BeetsItem] = []
        extra_tracks: list[BeetsTrackInfo] = []

        for tm in model.track_mappings:
            # mapping case
            if tm.track_info is not None and tm.item is not None:
                mapping[tm.item] = self.track_info_mapper.to_beets(tm.track_info, ctx)

            # extra track
            elif tm.track_info is not None:
                extra_tracks.append(self.track_info_mapper.to_beets(tm.track_info, ctx))

            # extra item
            elif tm.item is not None:
                extra_items.append(tm.item)

        return BeetsAlbumMatch(
            distance=self.distance_mapper.to_beets(model.distance, ctx),
            info=self.album_info_mapper.to_beets(model.info, ctx),
            mapping=mapping,
            extra_items=extra_items,
            extra_tracks=extra_tracks,
        )


class MatchMapper(BeetsMapper[BeetsAlbumMatch | BeetsTrackMatch, Match]):
    def __init__(self):
        self.album_mapper = AlbumMatchMapper()
        self.track_mapper = TrackMatchMapper()

    def _from_beets(
        self, obj: BeetsAlbumMatch | BeetsTrackMatch, ctx: Context
    ) -> Match:
        if isinstance(obj, BeetsAlbumMatch):
            return self.album_mapper.from_beets(obj, ctx)

        if isinstance(obj, BeetsTrackMatch):
            return self.track_mapper.from_beets(obj, ctx)

        raise TypeError(f"Unsupported beets obj type: {type(obj)}")

    def _to_beets(
        self, model: Match, ctx: Context
    ) -> BeetsAlbumMatch | BeetsTrackMatch:
        if isinstance(model, AlbumMatch):
            return self.album_mapper.to_beets(model, ctx)

        if isinstance(model, TrackMatch):
            return self.track_mapper.to_beets(model, ctx)

        raise TypeError(f"Unsupported model type: {type(model)}")
