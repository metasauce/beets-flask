import { ClockIcon } from 'lucide-react';
import { RowComponentProps } from 'react-window';
import { Box, Typography, useTheme } from '@mui/material';
import { Link } from '@tanstack/react-router';

import { CoverArt } from '@/components/library/coverArt';
import { AlbumResponseMinimal } from '@/pythonTypes';

import { LoadingCell, LoadingRow } from './loading';

import { AlbumIcon } from '../icons';
import { relativeTime } from '../units/time';

/** Props for the album browser components */
export interface AlbumBrowserProps {
    albums: Array<AlbumResponseMinimal>;
    showArt?: boolean;
    showArtist?: boolean;
    showYear?: boolean;
    /** When set, clicking a row selects the album instead of navigating to it. */
    onSelect?: (album: AlbumResponseMinimal) => void;
    /** Id of the album to highlight as selected. */
    selectedId?: number;
}

/** Row component for album list view */
export function AlbumListRow({
    albums,
    index,
    style,
    showArt = false,
    showArtist = true,
    showYear = true,
    onSelect,
    selectedId,
}: RowComponentProps<AlbumBrowserProps>) {
    const theme = useTheme();
    const album = albums.at(index);
    if (!album) {
        return <LoadingRow style={style} icon="album" />;
    }

    const content = (
        <Box
            sx={(theme) => ({
                height: style.height,
                display: 'flex',
                alignItems: 'center',
                paddingInline: 1,
                justifyContent: 'space-between',
                ...(album.id === selectedId
                    ? { backgroundColor: 'primary.muted' }
                    : {}),
                ':hover': {
                    background: `linear-gradient(to left, transparent 0%, ${theme.palette.primary.muted} 100%)`,
                    color: 'primary.contrastText',
                },
            })}
        >
            {showArt && (
                <CoverArt
                    type="album"
                    beetsId={album.id}
                    size="small"
                    sx={{
                        display: 'block',
                        width: '50px',
                        height: '50px',
                        padding: 0.5,
                    }}
                />
            )}

            <Box
                sx={{
                    display: 'flex',
                    flexDirection: 'column',
                    mr: 'auto',
                }}
            >
                <Typography
                    variant="body1"
                    fontWeight="bold"
                    color="text.primary"
                >
                    {album.name || 'Unknown Title'}{' '}
                    {showYear && !showArtist ? `(${album.year})` : ''}
                </Typography>
                {showArtist && (
                    <Typography variant="body2" color="text.secondary">
                        {album.albumartist} {showYear ? `(${album.year})` : ''}
                    </Typography>
                )}
            </Box>
            <AlbumIcon color={theme.palette.background.paper} />
        </Box>
    );

    if (onSelect) {
        return (
            <Box
                key={album.id}
                role="button"
                tabIndex={0}
                style={style}
                onClick={() => onSelect(album)}
                onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        onSelect(album);
                    }
                }}
            >
                {content}
            </Box>
        );
    }

    return (
        <Link
            to={`/library/album/$albumId`}
            key={album.id}
            params={{ albumId: album.id }}
            style={style}
        >
            {content}
        </Link>
    );
}

/** Grid cell component for album grid view */
export function AlbumGridCell({
    albums,
    index,
    style,
}: RowComponentProps<AlbumBrowserProps>) {
    const album = albums.at(index);
    if (!album) {
        return <LoadingCell style={style} />;
    }
    return (
        <Link
            to={`/library/album/$albumId`}
            key={album.id}
            params={{ albumId: album.id }}
            style={style}
        >
            <Box
                sx={{
                    width: style.width,
                    height: style.height,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    padding: 1,
                    textAlign: 'center',
                    ':hover': {
                        backgroundColor: 'primary.muted',
                        color: 'primary.contrastText',
                    },
                }}
            >
                <CoverArt
                    type="album"
                    beetsId={album.id}
                    sx={{
                        maxWidth: '100%',
                        maxHeight: '100%',
                        width: '200px',
                        height: '200px',
                        m: 0,
                    }}
                />
            </Box>
        </Link>
    );
}

/** Grid card for an album: cover art, title and when it was added.
 *
 * Used on the library home and the MusicBrainz album picker. When `onSelect`
 * is given the card becomes clickable to select the album instead of linking
 * to its library page. When `mbid` is set, a "On MusicBrainz" badge is shown.
 */
export function AlbumGridCard({
    album,
    selected = false,
    onSelect,
    mbid,
}: {
    album: AlbumResponseMinimal;
    selected?: boolean;
    onSelect?: (album: AlbumResponseMinimal) => void;
    mbid?: string;
}) {
    const theme = useTheme();

    const content = (
        <Box
            sx={{
                padding: 0.75,
                border: '2px solid',
                borderColor: selected ? 'primary.main' : 'primary.muted',
                width: '100%',
                color: 'primary.muted',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                gap: 1,
                height: '100%',
                borderRadius: 1,
                boxSizing: 'border-box',
            }}
        >
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
                <CoverArt
                    type="album"
                    beetsId={album.id}
                    sx={{ height: '92px', width: '92px', flexShrink: 0 }}
                />
                <Box
                    sx={{
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 0.5,
                        minWidth: 0,
                        flex: 1,
                    }}
                >
                    <Box
                        sx={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            gap: 0.75,
                        }}
                    >
                        <Typography
                            variant="h6"
                            sx={{
                                fontWeight: 600,
                                overflowWrap: 'anywhere',
                                lineHeight: 1.2,
                                minWidth: 0,
                            }}
                        >
                            {album.name || '[Unknown Album]'}
                        </Typography>
                        {mbid && (
                            <Box
                                sx={{
                                    flexShrink: 0,
                                    fontSize: 9,
                                    fontWeight: 700,
                                    textTransform: 'uppercase',
                                    letterSpacing: '0.4px',
                                    backgroundColor: 'primary.main',
                                    color: 'primary.contrastText',
                                    px: 0.75,
                                    py: 0.25,
                                    borderRadius: '8px',
                                    whiteSpace: 'nowrap',
                                }}
                            >
                                On MB
                            </Box>
                        )}
                    </Box>
                    <Box
                        sx={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 0.5,
                            color: 'grey.600',
                            letterSpacing: '1px',
                        }}
                    >
                        <ClockIcon size={theme.iconSize.md} />
                        <Typography variant="body2">
                            Added{' '}
                            {album.added
                                ? relativeTime(new Date(album.added))
                                : 'Unknown'}
                        </Typography>
                    </Box>
                </Box>
            </Box>
        </Box>
    );

    if (onSelect) {
        return (
            <Box
                key={album.id}
                role="button"
                tabIndex={0}
                onClick={() => onSelect(album)}
                onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        onSelect(album);
                    }
                }}
            >
                {content}
            </Box>
        );
    }

    return (
        <Link
            to={`/library/album/$albumId`}
            key={album.id}
            params={{ albumId: album.id }}
        >
            {content}
        </Link>
    );
}
