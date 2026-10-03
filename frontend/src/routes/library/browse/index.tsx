import {
    AudioLinesIcon,
    ChevronRight,
    ClockIcon,
    Disc3Icon,
    LibraryIcon,
    User2Icon,
} from 'lucide-react';
import { useMemo } from 'react';
import {
    Box,
    BoxProps,
    Button,
    Card,
    CardContent,
    Typography,
    useTheme,
} from '@mui/material';
import { useSuspenseQuery } from '@tanstack/react-query';
import { createFileRoute, Link } from '@tanstack/react-router';

import {
    Artist,
    artistsQueryOptions,
    recentAlbumsQueryOptions,
} from '@/api/library';
import { AlbumGridCard } from '@/components/common/browser/albums';
import { PageWrapper } from '@/components/common/page';
import { relativeTime } from '@/components/common/units/time';
import { CardHeader } from '@/components/frontpage/statsCard';

export const Route = createFileRoute('/library/browse/')({
    component: RouteComponent,
    loader: async (opts) => {
        const p1 = opts.context.queryClient.ensureQueryData(
            artistsQueryOptions()
        );
        const p2 = opts.context.queryClient.ensureQueryData(
            recentAlbumsQueryOptions
        );
        await Promise.all([p1, p2]);
    },
});

function RouteComponent() {
    return (
        <PageWrapper
            sx={(theme) => ({
                display: 'flex',
                flexDirection: 'column',
                height: '100%',
                width: '100%',
                alignItems: 'center',
                paddingTop: theme.spacing(1),
                paddingInline: theme.spacing(0.5),
                [theme.breakpoints.up('laptop')]: {
                    height: 'auto',
                    paddingTop: theme.spacing(2),
                    paddingInline: theme.spacing(1),
                },
                gap: 6,
                overflow: 'auto',
            })}
        >
            <PageHeader />
            <Albums />
            <Artists />
        </PageWrapper>
    );
}

function PageHeader(props: BoxProps) {
    return (
        <Box
            sx={{
                display: 'grid',
                alignItems: 'center',
                justifyContent: 'center',
                width: '100%',
                gridTemplateColumns: '1fr',
                gridTemplateRows: '1fr',
                paddingInline: 2,
            }}
            {...props}
        >
            <Box
                sx={{
                    alignSelf: 'center',
                    display: 'flex',
                    gap: 1,
                    zIndex: 1,
                    borderRadius: 1,
                    color: 'primary.muted',
                    gridColumn: '1',
                    gridRow: '1',
                    justifySelf: 'flex-start',
                }}
            >
                <LibraryIcon size={40} />
            </Box>
            <Typography
                variant="h4"
                component="div"
                fontWeight="bold"
                sx={{
                    gridColumn: '1',
                    gridRow: '1',
                    textAlign: 'center',
                }}
            >
                Browse your Library
            </Typography>
        </Box>
    );
}

/* --------------------------------- Albums --------------------------------- */

function Albums() {
    const { data: albums } = useSuspenseQuery(recentAlbumsQueryOptions);

    return (
        <Card sx={{ padding: 2, width: '100%', overflow: 'unset' }}>
            <CardHeader icon={<Disc3Icon size={36} />} size="large">
                <Typography variant="body1" color="text.secondary">
                    Albums
                </Typography>
            </CardHeader>
            <CardContent
                sx={{
                    paddingInline: 1,
                    paddingTop: 2,
                    m: 0,
                    paddingBottom: '0 !important',
                }}
            >
                <Box>
                    <Typography
                        variant="h5"
                        fontWeight={800}
                        letterSpacing={0.5}
                    >
                        Recently added
                    </Typography>
                    <Box
                        sx={{
                            display: 'grid',
                            gridTemplateColumns:
                                'repeat(auto-fill, minmax(300px, 1fr))',
                            gridAutoRows: 'auto',
                            gap: 1,
                            paddingTop: 2.5,
                        }}
                    >
                        {albums.slice(0, 6).map((album) => (
                            <AlbumGridCard key={album.id} album={album} />
                        ))}
                    </Box>
                </Box>

                <Box
                    sx={(theme) => ({
                        paddingTop: 3,
                        display: 'flex',
                        gap: 2,
                        fontWeight: 600,
                        justifyContent: 'flex-end',
                        [theme.breakpoints.down('tablet')]: {
                            '>*': {
                                width: '100%',
                            },
                        },
                    })}
                >
                    <Button
                        variant="contained"
                        endIcon={<ChevronRight />}
                        component={Link}
                        to="/library/browse/albums"
                        size="large"
                        sx={{
                            fontWeight: 600,
                        }}
                    >
                        All Albums
                    </Button>
                </Box>
            </CardContent>
        </Card>
    );
}

/* --------------------------------- Artists -------------------------------- */

function earliestAddedDate(artist: Artist) {
    return [artist.first_album_added, artist.first_item_added]
        .filter((d) => d instanceof Date)
        .reduce((min, d) => (d < min ? d : min));
}

function Artists() {
    const { data: artists } = useSuspenseQuery(artistsQueryOptions());

    const newAdditions = useMemo(() => {
        return artists.toSorted((a, b) => {
            const earliestDateA = earliestAddedDate(a);
            const earliestDateB = earliestAddedDate(b);
            return earliestDateB.getTime() - earliestDateA.getTime();
        });
    }, [artists]);

    const topArtistsByItems = useMemo(() => {
        return artists
            .filter((a) => a.item_count > 0)
            .toSorted((a, b) => b.item_count - a.item_count);
    }, [artists]);

    return (
        <Card sx={{ padding: 2, width: '100%', overflow: 'unset' }}>
            <CardHeader icon={<User2Icon size={36} />} size="large">
                <Typography variant="body1" color="text.secondary">
                    Artists
                </Typography>
            </CardHeader>
            <CardContent
                sx={{
                    paddingInline: 1,
                    paddingTop: 2,
                    m: 0,
                    paddingBottom: '0 !important',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 3,
                }}
            >
                <Box>
                    <Typography
                        variant="h5"
                        fontWeight={800}
                        letterSpacing={0.5}
                    >
                        Top occurring Artists
                    </Typography>
                    <Box
                        sx={{
                            display: 'grid',
                            gridTemplateColumns:
                                'repeat(auto-fill, minmax(200px, 1fr))',
                            gridAutoRows: '1fr',
                            gap: 1,
                            paddingTop: 2.5,
                        }}
                    >
                        {topArtistsByItems.slice(0, 10).map((artist) => {
                            return (
                                <ArtistCardCounts
                                    key={artist.artist}
                                    {...artist}
                                />
                            );
                        })}
                    </Box>
                </Box>
                <Box>
                    <Typography
                        variant="h5"
                        fontWeight={800}
                        letterSpacing={0.5}
                    >
                        New additions
                    </Typography>
                    <Box
                        sx={{
                            display: 'grid',
                            gridTemplateColumns:
                                'repeat(auto-fill, minmax(220px, 1fr))',
                            gridAutoRows: '1fr',
                            gap: 1,
                            paddingTop: 2.5,
                        }}
                    >
                        {newAdditions.slice(0, 10).map((artist) => {
                            return (
                                <ArtistCardAdded
                                    key={artist.artist}
                                    {...artist}
                                />
                            );
                        })}
                    </Box>
                </Box>
                <Box
                    sx={(theme) => ({
                        paddingTop: 3,
                        display: 'flex',
                        gap: 2,
                        fontWeight: 600,
                        justifyContent: 'flex-end',
                        [theme.breakpoints.down('tablet')]: {
                            '>*': {
                                width: '100%',
                            },
                        },
                    })}
                >
                    <Button
                        variant="contained"
                        endIcon={<ChevronRight />}
                        component={Link}
                        to="/library/browse/artists"
                        size="large"
                        sx={{
                            fontWeight: 600,
                        }}
                    >
                        All Artists
                    </Button>
                </Box>
            </CardContent>
        </Card>
    );
}

function ArtistCardCounts({
    artist: name,
    album_count: nAlbums,
    item_count: nTracks,
}: Artist) {
    const theme = useTheme();

    return (
        <Box
            sx={{
                padding: 0.5,
                border: '2px solid',
                borderColor: 'primary.muted',
                width: '100%',
                color: 'primary.muted',
                display: 'flex',
                alignItems: 'center',
                flexDirection: 'column',
                borderRadius: 1,
                a: {
                    width: '100%',
                },
            }}
        >
            <Link
                to="/library/browse/artists/$artist"
                params={{ artist: name }}
            >
                <Box
                    sx={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: 1,
                        color: 'grey.600',
                        letterSpacing: '1px',
                        width: '100%',
                    }}
                >
                    <Box
                        sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}
                    >
                        <Disc3Icon size={theme.iconSize.md} />
                        <Typography variant="body2">
                            {nAlbums} Album{nAlbums !== 1 ? 's' : ''}
                        </Typography>
                    </Box>
                    <Box
                        sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}
                    >
                        <AudioLinesIcon size={theme.iconSize.md} />
                        <Typography variant="body2">
                            {nTracks} Track{nTracks !== 1 ? 's' : ''}
                        </Typography>
                    </Box>
                </Box>
                <Typography
                    variant="h6"
                    sx={{
                        fontWeight: 600,
                        lineHeight: 1.1,
                        overflowWrap: 'anywhere',
                        paddingLeft: 1,
                        paddingBlock: 0.5,
                        textAlign: 'right',
                        width: '100%',
                    }}
                >
                    {name}
                </Typography>
            </Link>
        </Box>
    );
}

function ArtistCardAdded(artist: Artist) {
    const theme = useTheme();

    const added = earliestAddedDate(artist);
    const name = artist.artist;

    return (
        <Box
            sx={{
                padding: 0.5,
                border: '2px solid',
                borderColor: 'primary.muted',
                width: '100%',
                color: 'primary.muted',
                display: 'flex',
                alignItems: 'center',
                flexDirection: 'column',
                borderRadius: 1,
                a: {
                    width: '100%',
                },
            }}
        >
            <Link
                to="/library/browse/artists/$artist"
                params={{ artist: name }}
            >
                <Box
                    sx={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: 1,
                        color: 'grey.600',
                        letterSpacing: '1px',
                        width: '100%',
                    }}
                >
                    <Box
                        sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}
                    >
                        <ClockIcon size={theme.iconSize.md} />
                        <Typography variant="body2">
                            Added {added ? relativeTime(added) : 'Unknown'}
                        </Typography>
                    </Box>
                </Box>
                <Typography
                    variant="h6"
                    sx={{
                        fontWeight: 600,
                        lineHeight: 1.1,
                        overflowWrap: 'anywhere',
                        paddingLeft: 1,
                        paddingBlock: 0.5,
                        textAlign: 'right',
                        width: '100%',
                    }}
                >
                    {name}
                </Typography>
            </Link>
        </Box>
    );
}
