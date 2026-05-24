import { FileWarningIcon } from 'lucide-react';
import { useState } from 'react';
import { Button } from '@mui/material';
import Box, { BoxProps } from '@mui/material/Box';
import Skeleton from '@mui/material/Skeleton';
import { SxProps } from '@mui/material/styles';
import { useQuery } from '@tanstack/react-query';

import { HTTPError } from '@/api/common';
import {
    artQueryOptions,
    ArtSize,
    externalArtQueryOptions,
    fileArtQueryOptions,
    numArtQueryOptions,
} from '@/api/library';

import missingCoverImage from '@/assets/missing_cover.webp';

export interface CoverArtProps extends BoxProps {
    size?: ArtSize;
    index?: number;
    showPlaceholder?: boolean;
}

/** Cover art for an item or album
 *
 * Shows the cover art for an item or album in the beets library.
 */
export function CoverArt({
    type,
    beetsId,
    size = 'medium',
    sx,
    index,
    ...props
}: CoverArtProps & { type: 'item' | 'album'; beetsId: number }) {
    const query = useQuery(
        artQueryOptions({ type, id: beetsId, size, index: index })
    );
    return <CoverArtFromQuery query={query} size={size} sx={sx} {...props} />;
}

/** Cover art for a file path
 *
 * Shows the cover art for a specific file.
 */
export function FileCoverArt({
    path,
    size = 'medium',
    sx,
    index,
    ...props
}: CoverArtProps & { path: string }) {
    const query = useQuery(fileArtQueryOptions({ path, size, index }));
    return <CoverArtFromQuery query={query} size={size} sx={sx} {...props} />;
}

/** Cover art from an external data URL
 */
export function ExternalCoverArt({
    data_url,
    sx,
    ...props
}: CoverArtProps & { data_url: string }) {
    const query = useQuery(externalArtQueryOptions(data_url));
    return <CoverArtFromQuery query={query} sx={sx} size="medium" {...props} />;
}

/** A bit more complex version of the normal cover.
 *
 * Allows to show all artworks of a given item by cycling through them.
 */
export function MultiCoverArt({
    beetsId,
    size,
    coverArtSx,
    ...props
}: CoverArtProps & { beetsId: number; coverArtSx?: BoxProps['sx'] }) {
    const [currentIdx, setCurrentIdx] = useState(0);

    const { data: numArtworks } = useQuery(numArtQueryOptions(beetsId));

    return (
        <Box position="relative" {...props}>
            {numArtworks && numArtworks.count > 1 && (
                <Button
                    variant="text"
                    sx={{
                        position: 'absolute',
                        top: 0,
                        right: 0,
                        m: 0,
                        p: 1,
                        minWidth: 0,
                    }}
                    onClick={() => {
                        setCurrentIdx((prev) => (prev + 1) % numArtworks.count);
                    }}
                >
                    {
                        //Dot for each artwork
                        Array.from({ length: numArtworks.count }).map(
                            (_, idx) => (
                                <Box
                                    key={idx}
                                    sx={{
                                        width: 8,
                                        height: 8,
                                        borderRadius: '50%',
                                        backgroundColor:
                                            currentIdx === idx
                                                ? 'primary.main'
                                                : 'text.secondary',
                                        marginLeft: 0.5,
                                    }}
                                />
                            )
                        )
                    }
                </Button>
            )}
            <CoverArt
                type="item"
                beetsId={beetsId}
                size={size}
                index={currentIdx}
                sx={[
                    {
                        maxWidth: '100%',
                        maxHeight: '100%',
                        width: 'auto',
                        height: '100%',
                        aspectRatio: '1 / 1',
                        m: 0,
                        borderRadius: 2,
                        objectFit: 'contain',
                    },
                    // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
                    ...(Array.isArray(coverArtSx) ? coverArtSx : [coverArtSx]),
                ]}
            />
        </Box>
    );
}

/* -------------------------------- Helpers --------------------------------- */

function CoverArtFromQuery({
    query,
    size = 'medium',
    sx,
    showPlaceholder = true,
    ...props
}: {
    query: ReturnType<typeof useQuery<string | null>>;
    size: ArtSize;
    showPlaceholder?: boolean;
} & Partial<BoxProps>) {
    const coverSx = [
        {
            height: 100,
            width: 100,
            aspectRatio: '1 / 1',
            overflow: 'hidden',
        },
        // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
        ...(Array.isArray(sx) ? sx : [sx]),
    ] as SxProps;

    const { data: art, isPending, isError, error } = query;

    if (isPending) {
        return (
            <CoverArtPlaceholder
                sx={coverSx}
                animation="wave"
                showPlaceholder={showPlaceholder}
                {...props}
            />
        );
    }

    if (isError) {
        const coverArtError =
            error instanceof HTTPError
                ? error
                : new HTTPError(error?.message || String(error));

        return (
            <CoverArtError
                sx={coverSx}
                error={coverArtError}
                size={size}
                {...props}
            />
        );
    }

    if (art) {
        return <CoverArtContent sx={coverSx} src={art} {...props} />;
    } else {
        return (
            <CoverArtPlaceholder
                sx={coverSx}
                animation={false}
                showPlaceholder={showPlaceholder}
                {...props}
            />
        );
    }
}

function CoverArtPlaceholder({
    animation,
    showPlaceholder = true,
    ...props
}: {
    animation: false | 'pulse' | 'wave' | undefined;
    showPlaceholder?: boolean;
} & Partial<BoxProps>) {
    return (
        <Box {...props}>
            <Skeleton
                variant="rectangular"
                animation={animation}
                height="100%"
                width="100%"
                sx={{
                    display: showPlaceholder ? 'block' : 'none',
                }}
            />
        </Box>
    );
}

function CoverArtContent({
    src,
    ...props
}: { src: string } & Partial<BoxProps>) {
    return <Box component="img" src={src} {...props} />;
}

function CoverArtError({
    error,
    size,
    ...props
}: { error: HTTPError; size: ArtSize } & Partial<BoxProps>) {
    console.warn('CoverArtError', error);

    if (error.statusCode === 404) {
        return (
            <Box
                {...props}
                sx={[
                    (theme) => ({
                        backgroundColor: theme.vars
                            ? theme.vars.palette.Skeleton.bg
                            : theme.alpha(
                                  theme.palette.text.primary,
                                  theme.palette.mode === 'light' ? 0.11 : 0.13
                              ),
                    }),
                    // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
                    ...(Array.isArray(props.sx) ? props.sx : [props.sx]),
                ]}
            >
                <Box
                    component="img"
                    src={missingCoverImage}
                    sx={{
                        width: '100%',
                        height: '100%',
                        opacity: 0.5,
                        padding: 1,
                    }}
                />
            </Box>
        );
    }

    return (
        <Box {...props}>
            <Box
                sx={{
                    width: '100%',
                    height: '100%',
                    display: 'flex',
                    justifyContent: 'center',
                    alignItems: 'center',
                    fontSize: '2rem',
                    border: '1px solid',
                    color: 'error.main',
                    flexDirection: 'column',
                    gap: 1,
                    p: 0.5,
                }}
            >
                <FileWarningIcon size={50} strokeWidth={2} />
                {size === 'large' && (
                    <Box
                        sx={{
                            width: '100%',
                            alignItems: 'center',
                            fontSize: '0.8rem',
                            color: 'error.main',
                            p: 1,
                        }}
                    >
                        <b>{error.name}</b> - {error.message}
                    </Box>
                )}
            </Box>
        </Box>
    );
}
