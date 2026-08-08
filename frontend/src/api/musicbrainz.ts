import { queryOptions } from '@tanstack/react-query';

import type { PreparedRelease } from '@/pythonTypes';

// Status of the MusicBrainz assistant (endpoint availability + editor url)
export const musicbrainzStatusQueryOptions = () =>
    queryOptions({
        queryKey: ['musicbrainz', 'status'],
        queryFn: async () => {
            const response = await fetch(`/musicbrainz/status`);
            return (await response.json()) as {
                enabled: boolean;
                editor_url: string;
                ws_url: string;
                check_artists: boolean;
            };
        },
    });

// Prepare an album from the beets library for the MusicBrainz release editor
export const prepareReleaseQueryOptions = (albumId: number) => ({
    queryKey: ['musicbrainz', 'prepare', albumId],
    queryFn: async () => {
        const response = await fetch(`/musicbrainz/prepare`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ albumId }),
        });
        return (await response.json()) as PreparedRelease;
    },
});

export type AlbumExists = {
    album_id: number;
    exists: boolean;
    mbid: string | null;
};

// Whether a beets album is already on MusicBrainz. Stored mb_albumids short
// circuit server side; otherwise the release is looked up by barcode.
export const albumExistsQueryOptions = (albumId: number, enabled = true) => ({
    queryKey: ['musicbrainz', 'album_exists', albumId],
    enabled,
    staleTime: 24 * 60 * 60 * 1000,
    queryFn: async () => {
        const response = await fetch(`/musicbrainz/album_exists/${albumId}`);
        return (await response.json()) as AlbumExists;
    },
});
