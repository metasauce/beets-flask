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

// An album folder in the inbox and its MusicBrainz match info. The match
// percentage comes from the most recent import session of the folder.
export type InboxAlbum = {
    folder_path: string;
    folder_hash: string;
    type: 'directory' | 'archive';
    name: string | null;
    albumartist: string | null;
    year: string | null;
    match_percentage: number | null;
    match_mbid: string | null;
    has_session: boolean;
    has_match: boolean;
};

// All albums currently in the inbox, with their MusicBrainz match info
export const musicbrainzInboxAlbumsQueryOptions = () => ({
    queryKey: ['musicbrainz', 'albums'],
    queryFn: async () => {
        const response = await fetch(`/musicbrainz/albums`);
        return (await response.json()) as InboxAlbum[];
    },
});

// Percent-encode the folder path without its leading slash: slashes become
// %2F (which the backend decodes) and the backend restores the leading slash.
// Encoding the leading slash too (%2F...) breaks Werkzeug's <path:> routing,
// which then falls through to the SPA catch-all (index.html).
const inboxFolderSegment = (folderPath: string) =>
    encodeURIComponent(folderPath.replace(/^\//, ''));

// Prepare an inbox album for the MusicBrainz release editor
export const prepareInboxReleaseQueryOptions = (folderPath: string) => ({
    queryKey: ['musicbrainz', 'prepare', 'inbox', folderPath],
    queryFn: async () => {
        const response = await fetch(
            `/musicbrainz/prepare/${inboxFolderSegment(folderPath)}`
        );
        return (await response.json()) as PreparedRelease;
    },
});

export type InboxAlbumExists = {
    folder_path: string;
    exists: boolean;
    mbid: string | null;
};

// Whether an inbox album is already on MusicBrainz. A session match close
// enough to be auto-imported short circuits server side; otherwise the
// release is looked up by barcode.
export const inboxAlbumExistsQueryOptions = (
    folderPath: string,
    enabled = true
) => ({
    queryKey: ['musicbrainz', 'album_exists', 'inbox', folderPath],
    enabled,
    staleTime: 24 * 60 * 60 * 1000,
    queryFn: async () => {
        const response = await fetch(
            `/musicbrainz/album_exists/${inboxFolderSegment(folderPath)}`
        );
        return (await response.json()) as InboxAlbumExists;
    },
});
