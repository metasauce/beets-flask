import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query';

import { toHex } from '@/components/common/strings';
import { parseApiDate } from '@/components/common/units/time';
import {
    AlbumResponse,
    AlbumResponseExpanded,
    AlbumResponseMinimal,
    AlbumResponseMinimalExpanded,
    ItemResponse,
    ItemResponseMinimal,
    LibraryStats as _LibraryStats,
} from '@/pythonTypes';

import { queryClient } from './common';

export type LibraryStats = Omit<
    _LibraryStats,
    'lastItemAdded' | 'lastItemModified'
> & {
    lastItemAdded?: Date;
    lastItemModified?: Date;
};

// Some stats about the library
export const libraryStatsQueryOptions = () => {
    return queryOptions({
        queryKey: ['libraryStats'],
        queryFn: async () => {
            const response = await fetch(`/library/stats`);
            const dat = (await response.json()) as _LibraryStats;

            return {
                ...dat,
                lastItemAdded: dat.lastItemAdded
                    ? new Date(dat.lastItemAdded)
                    : undefined,
                lastItemModified: dat.lastItemModified
                    ? new Date(dat.lastItemModified)
                    : undefined,
            } as LibraryStats;
        },
    });
};

interface AlbumResponseFull extends AlbumResponse {
    [key: string]: unknown; // enable indexing album[key]
}

export type Album<
    Expand extends boolean,
    Minimal extends boolean,
> = Minimal extends true
    ? Expand extends true
        ? AlbumResponseMinimalExpanded
        : AlbumResponseMinimal
    : Expand extends true
      ? AlbumResponseExpanded
      : AlbumResponseFull;

export interface ItemResponseFull extends ItemResponse {
    [key: string]: unknown; // enable indexing item[key]
}

export type Item<Minimal extends boolean> = Minimal extends true
    ? ItemResponseMinimal
    : ItemResponseFull;

function _url_parse_minimal_expand(
    url: string,
    minimal: boolean = false,
    expand: boolean = false
) {
    const params = [];
    if (minimal) {
        params.push('minimal');
    }
    if (expand) {
        params.push('expand');
    }
    return params.length ? `${url}?${params.join('&')}` : url;
}

// An item by its ID
export const itemQueryOptions = <Minimal extends boolean>(
    id: number,
    minimal: Minimal = true as Minimal
) => ({
    queryKey: ['item', id, minimal],
    queryFn: async (): Promise<Item<typeof minimal>> => {
        const url = _url_parse_minimal_expand(`/library/item/${id}`, minimal);
        const response = await fetch(url);
        return (await response.json()) as Item<typeof minimal>;
    },
});

interface ItemsPageResponse {
    items: ItemResponseMinimal[];
    total: number;
    next: string | null;
}

export const itemsInfiniteQueryOptions = ({
    query,
    orderBy,
    orderDirection = 'ASC',
}: {
    query: string;
    orderBy?: 'title';
    orderDirection?: 'ASC' | 'DESC';
}) => {
    const params = new URLSearchParams();
    params.set('n_items', '100'); // Number of items per page
    if (orderBy) params.set('order_by', orderBy);
    if (orderDirection) params.set('order_dir', orderDirection);
    const paramsStr = params.toString();

    let initUrl = `/api_v1/library/items`;
    if (query) {
        initUrl += `/${encodeURIComponent(query)}`;
    }
    if (paramsStr) {
        initUrl += `?${paramsStr}`;
    }

    return infiniteQueryOptions({
        queryKey: ['items', query, orderBy, orderDirection],
        queryFn: async ({ pageParam }) => {
            const response = await fetch(pageParam.replace('/api_v1', ''));
            return (await response.json()) as ItemsPageResponse;
        },
        initialPageParam: initUrl,
        getNextPageParam: (lastPage) => {
            return lastPage.next;
        },
        select: (data) => {
            return {
                items: data.pages.flatMap((page) => page.items),
                total: data.pages.at(-1)?.total ?? 0,
            };
        },
    });
};

/* --------------------------------- Albums --------------------------------- */

// An album imported by us
export const albumImportedOptions = <
    Expand extends boolean,
    Minimal extends boolean,
>(
    task_id: string,
    expand: Expand = true as Expand,
    minimal: Minimal = true as Minimal
) => ({
    queryKey: ['album', task_id, expand, minimal],
    queryFn: async (): Promise<Album<typeof expand, typeof minimal>> => {
        const url = _url_parse_minimal_expand(
            `/library/album/bf_id/${task_id}`,
            minimal,
            expand
        );
        const response = await fetch(url);
        return (await response.json()) as Album<typeof expand, typeof minimal>;
    },
    retry: 1,
});

// An album by its ID
export const albumQueryOptions = <
    Expand extends boolean,
    Minimal extends boolean,
>(
    id: number,
    expand: Expand = true as Expand,
    minimal: Minimal = true as Minimal
) => ({
    queryKey: ['album', id, expand, minimal],
    queryFn: async (): Promise<Album<typeof expand, typeof minimal>> => {
        console.log('albumQueryOptions', id, expand, minimal);
        const url = _url_parse_minimal_expand(
            `/library/album/${id}`,
            minimal,
            expand
        );
        const response = await fetch(url);
        console.log('albumQueryOptions response', response);
        return (await response.json()) as Album<typeof expand, typeof minimal>;
    },
});

interface AlbumsPageResponse {
    albums: AlbumResponseMinimal[];
    total: number;
    next: string | null;
}

// Infinite query for all albums with search
export const albumsInfiniteQueryOptions = ({
    query,
    orderBy,
    orderDirection = 'ASC',
}: {
    query: string;
    orderBy?: 'album' | 'albumartist' | 'year';
    orderDirection?: 'ASC' | 'DESC';
}) => {
    const params = new URLSearchParams();
    params.set('n_items', '50'); // Number of items per page
    if (orderBy) params.set('order_by', orderBy);
    if (orderDirection) params.set('order_dir', orderDirection);
    const paramsStr = params.toString();

    let initUrl = `/api_v1/library/albums`;
    if (query) {
        initUrl += `/${encodeURIComponent(query)}`;
    }
    if (paramsStr) {
        initUrl += `?${paramsStr}`;
    }

    return infiniteQueryOptions({
        queryKey: ['albums', query, orderBy, orderDirection],
        queryFn: async ({ pageParam }) => {
            const response = await fetch(pageParam.replace('/api_v1', ''));
            return (await response.json()) as AlbumsPageResponse;
        },
        initialPageParam: initUrl,
        getNextPageParam: (lastPage) => {
            return lastPage.next;
        },
        select: (data) => {
            return {
                albums: data.pages.flatMap((page) => page.albums),
                total: data.pages.at(-1)?.total ?? 0,
            };
        },
    });
};

export const recentAlbumsQueryOptions = {
    queryKey: ['recentAlbums'],
    queryFn: async () => {
        const response = await fetch(
            `/library/albums?order_by=added&order_dir=DESC&n_items=25`
        );
        const page = (await response.json()) as AlbumsPageResponse;
        return page.albums.map((album) => {
            album.added = new Date(album.added);
            return album;
        });
    },
};

/* --------------------------------- Artists -------------------------------- */

export interface Artist {
    artist: string;
    album_count: number;
    item_count: number;
    last_item_added?: Date;
    last_album_added?: Date;
    first_item_added?: Date;
    first_album_added?: Date;
}

// List of all artists
export const artistsQueryOptions = () => ({
    queryKey: ['artists'],
    queryFn: async () => {
        const response = await fetch(`/library/artists/`);
        const artists = (await response.json()) as Artist[];

        for (let i = 0; i < artists.length; i++) {
            const artist = artists[i];
            artist.last_item_added = parseApiDate(artist.last_item_added);
            artist.last_album_added = parseApiDate(artist.last_album_added);
            artist.first_item_added = parseApiDate(artist.first_item_added);
            artist.first_album_added = parseApiDate(artist.first_album_added);
        }
        return artists;
        // TODO: fill cache data for single artists queries
    },
    refetchOnWindowFocus: 'always' as const,
});

// An artist by its name
export const artistQueryOptions = (name: string) => ({
    queryKey: ['artist', name],
    queryFn: async () => {
        const response = await fetch(`/library/artists/${name}`);
        return (await response.json()) as Artist;
    },
    refetchOnWindowFocus: 'always' as const,
});

// All albums for a specific artist
export const albumsByArtistQueryOptions = <
    Expand extends boolean,
    Minimal extends boolean,
>(
    name: string,
    expand: Expand = true as Expand,
    minimal: Minimal = true as Minimal
) => ({
    queryKey: ['artist', name, expand, minimal],
    queryFn: async (): Promise<Album<typeof expand, typeof minimal>[]> => {
        const url = _url_parse_minimal_expand(
            `/library/artist/${name}/albums`,
            minimal,
            expand
        );
        const response = await fetch(url);
        return (await response.json()) as Album<
            typeof expand,
            typeof minimal
        >[];
    },
});

// All items for a specific artist
export const itemsByArtistQueryOptions = <Minimal extends boolean>(
    name: string,
    minimal: Minimal = true as Minimal
) => ({
    queryKey: ['artist', name, 'items', minimal],
    queryFn: async (): Promise<Item<typeof minimal>[]> => {
        const url = _url_parse_minimal_expand(
            `/library/artist/${name}/items`,
            minimal
        );
        const response = await fetch(url);
        return (await response.json()) as Item<typeof minimal>[];
    },
});

/* --------------------------------- Artwork -------------------------------- */

export type ArtSize = 'small' | 'medium' | 'large' | 'original';

const ART_QUERY_OPTIONS = {
    retry: false,
    gcTime: 1000 * 60 * 60 * 24, // 1 day
    staleTime: 1000 * 60 * 60 * 24, // 1 day
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false, // Prevent refetch on network reconnect
};

// Art for a library item or album
export const artUrl = (
    type: 'item' | 'album',
    id: number,
    size?: ArtSize,
    idx?: number
) => {
    const params = new URLSearchParams();
    if (size) params.set('size', size);
    if (idx !== undefined) params.set('idx', idx.toString());

    const base = `/library/${type}/${id}/art`;
    return params.toString() ? `${base}?${params}` : base;
};

export const artQueryOptions = ({
    type,
    id,
    size,
    index,
}: {
    type?: 'item' | 'album';
    id?: number;
    size?: ArtSize;
    index?: number;
}) =>
    queryOptions({
        queryKey: ['art', type, id, size, index],
        queryFn: async () => {
            if (id == null || !type) {
                return null;
            }
            const url = artUrl(type, id, size, index);
            const response = await fetch(url);
            const blob = await response.blob();
            const objectUrl = URL.createObjectURL(blob);
            return objectUrl;
        },
        retryOnMount: false,
        ...ART_QUERY_OPTIONS,
    });

// Number of artworks for an item -> back, front, etc.
export const numArtQueryOptions = (itemId?: number) =>
    queryOptions({
        queryKey: ['art', 'num', itemId],
        queryFn: async () => {
            if (itemId == null) {
                return null;
            }
            const response = await fetch(`/library/item/${itemId}/nArtworks`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                },
            });
            return (await response.json()) as { count: number };
        },
        ...ART_QUERY_OPTIONS,
        retry: 1,
    });

export const fileArtQueryOptions = ({
    path,
    size,
    index,
}: {
    path: string;
    size?: ArtSize;
    index?: number;
}) =>
    queryOptions({
        queryKey: ['fileArt', path, size, index],
        queryFn: async () => {
            const encodedPath = toHex(path);
            const params = new URLSearchParams();
            if (size) params.set('size', size);
            if (index !== undefined) params.set('idx', index.toString());

            const base = `/library/file/${encodedPath}/art`;
            const url = params.toString() ? `${base}?${params}` : base;
            const response = await fetch(url);
            const blob = await response.blob();
            const objectUrl = URL.createObjectURL(blob);
            return objectUrl;
        },
        retryOnMount: false,
        ...ART_QUERY_OPTIONS,
    });

export const numFileArtQueryOptions = (filePath: string) =>
    queryOptions({
        queryKey: ['fileArt', 'num', filePath],
        queryFn: async () => {
            const encodedPath = toHex(filePath);
            const response = await fetch(
                `/library/file/${encodedPath}/nArtworks`,
                {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                }
            );
            return (await response.json()) as { count: number };
        },
        ...ART_QUERY_OPTIONS,
        retry: 1,
    });

export const externalArtQueryOptions = (data_url: string) =>
    queryOptions({
        queryKey: ['externalArt', data_url],
        queryFn: async () => {
            const blob = await fetch(
                `/art?url=${encodeURIComponent(data_url)}`
            ).then((r) => r.blob());

            const dataUrl: string = await new Promise((resolve) => {
                const reader = new FileReader();
                reader.onload = () => resolve(reader.result as string);
                reader.readAsDataURL(blob);
            });
            return dataUrl;
        },
    });

/* ---------------------------- Waveforms / Peaks --------------------------- */
// We precompute the waveform for each audio file on the server
// allows to show the waveform without loading the entire audio file first

const commonAudioQueryOptions = {
    staleTime: 1000 * 60 * 5, // 5 minutes
    gcTime: 1000 * 60 * 10, // 10 minutes
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
};

async function fetchWaveform(url: string, signal: AbortSignal) {
    const response = await fetch(url, { signal });
    const blob = await response.blob();
    const arrayBuffer = await blob.arrayBuffer();
    const data = new Float32Array(arrayBuffer);
    return data;
}
export function waveformQueryOptions(id?: number) {
    return queryOptions({
        queryKey: ['item', 'audio', 'waveform', id],
        queryFn: async ({ signal }) => {
            if (!id) {
                return null;
            }
            return await fetchWaveform(
                `/library/item/${id}/audio/peaks`,
                signal
            );
        },
        retry: false,
        ...commonAudioQueryOptions,
    });
}

export function prefetchWaveform(id: number) {
    return queryClient.prefetchQuery({
        queryKey: ['item', 'audio', 'waveform', id],
        queryFn: async ({ signal }) => {
            return await fetchWaveform(
                `/library/item/${id}/audio/peaks`,
                signal
            );
        },
        ...commonAudioQueryOptions,
    });
}

/* ------------------------------- Audio files ------------------------------ */
// We add progress to the cache to allow inflight merging
// or prefetched and new queries

async function fetchAudio(
    id: number,
    signal: AbortSignal
): Promise<HTMLAudioElement> {
    const mimeCodecs = 'audio/webm; codecs=opus';
    const audio = new Audio();

    if (!MediaSource.isTypeSupported(mimeCodecs)) {
        console.warn('Audio streaming not supported, using fallback');
        const res = await fetch(`/library/item/${id}/audio`, { signal });
        audio.src = URL.createObjectURL(await res.blob());
        return audio;
    }

    const mediaSource = new MediaSource();
    let resolveSourceBuffer: (buffer: SourceBuffer) => void;

    // Create a promise to resolve when SourceBuffer is ready
    const sourceBufferReady = new Promise<SourceBuffer>((resolve) => {
        resolveSourceBuffer = resolve;
    });

    // Start fetch outside sourceopen
    const response = await fetch(`/library/item/${id}/audio`, { signal });
    if (!response.body)
        throw new Error(`Fetch error: ${response.status} no body!`);

    // Set up sourceopen handler (queues data until ready)
    mediaSource.addEventListener(
        'sourceopen',
        () => {
            const sourceBuffer = mediaSource.addSourceBuffer(mimeCodecs);
            sourceBuffer.mode = 'sequence';
            resolveSourceBuffer(sourceBuffer);
        },
        { once: true }
    );

    (async () => {
        /** Warning: This is an absolute mess, I spend quite some time
         * here and tried to remove all race conditions
         * and add buffering to the audio stream.
         * Proceed with caution :)
         *
         * ref: https://developer.mozilla.org/en-US/docs/Web/API/MediaSource
         */
        audio.src = URL.createObjectURL(mediaSource);
        const sourceBuffer = await sourceBufferReady; // wait for sourceBuffer to be ready
        const contentLengthHeader = response.headers.get('Content-Length');
        const _total = contentLengthHeader
            ? parseInt(contentLengthHeader, 10)
            : null;
        const reader = response.body!.getReader();

        // Process the stream
        let isAppending = false;
        let isEndOfStream = false;
        const appendQueue: ArrayBuffer[] = [];

        function processAppendQueue() {
            if (!isAppending && appendQueue.length > 0) {
                isAppending = true;
                const chunk = appendQueue.shift();
                if (chunk) {
                    sourceBuffer.appendBuffer(chunk);
                }
            }
        }

        function endStream() {
            if (isAppending) {
                isEndOfStream = true;
            } else {
                mediaSource.endOfStream();
            }
        }

        sourceBuffer.addEventListener('updateend', () => {
            isAppending = false;
            if (isEndOfStream && appendQueue.length === 0) {
                mediaSource.endOfStream();
            }
            processAppendQueue();
        });

        function appendChunk(chunk: ArrayBuffer) {
            appendQueue.push(chunk);
            processAppendQueue();
        }

        async function appendToBuffer() {
            // Read the data
            let _loaded = 0;
            while (true) {
                const { done, value } = await reader.read();
                if (done) {
                    endStream();
                    break;
                }

                _loaded += value.length;
                // NOTE: In theory we can add a
                // onProgress event here
                // but it is not clear if the total
                // length is known
                // log.debug(`Loaded ${loaded} bytes`);

                appendChunk(value.buffer);
            }
        }

        await appendToBuffer();
    })().catch(console.error);

    /** No idea why but we need a short delay here to kick
     * into the micro task queue, only needed in chromium
     * based browsers. Maybe browser bug
     */
    await new Promise((resolve) => {
        setTimeout(() => {
            resolve(true);
        }, 200);
    });

    return audio;
}

export function itemAudioDataQueryOptions(id?: number) {
    return queryOptions({
        queryKey: ['item', 'audio', id],
        queryFn: async ({ signal }) => {
            if (!id) {
                return null;
            }
            return await fetchAudio(id, signal);
        },
        ...commonAudioQueryOptions,
    });
}

export function prefetchItemAudioData(id: number) {
    return queryClient.prefetchQuery({
        queryKey: ['item', 'audio', id],
        queryFn: async ({ signal }) => {
            return await fetchAudio(id, signal);
        },
        ...commonAudioQueryOptions,
    });
}

/* -------------------------------- Metadata -------------------------------- */

// fetch metadata for files, directly from id3
export type FileMetadata = {
    [key: string]: string | number | boolean | string[];
};

export const fileMetadataQueryOptions = (path: string) => ({
    queryKey: ['file', path, 'metadata'],
    queryFn: async () => {
        const encodedPath = toHex(path);
        const response = await fetch(`/library/file/${encodedPath}/metadata`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            },
        });
        return (await response.json()) as FileMetadata;
    },
});
