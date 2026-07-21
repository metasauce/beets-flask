import { useEffect, useState } from 'react';
import { List, ListProps } from 'react-window';
import { Box, BoxProps, Divider, Typography, useTheme } from '@mui/material';
import { useInfiniteQuery } from '@tanstack/react-query';
import { createFileRoute } from '@tanstack/react-router';

import { albumsInfiniteQueryOptions } from '@/api/library';
import {
    AlbumGridCell,
    AlbumListRow,
} from '@/components/common/browser/albums';
import { useDebounce } from '@/components/common/hooks/useDebounce';
import {
    getStorageValue,
    useLocalStorage,
} from '@/components/common/hooks/useLocalStorage';
import { AlbumIcon } from '@/components/common/icons';
import { BackIconButton } from '@/components/common/inputs/back';
import { Search } from '@/components/common/inputs/search';
import { PageWrapper } from '@/components/common/page';
import {
    CurrentSort,
    DynamicFlowGrid,
    DynamicFlowGridProps,
    SortToggle,
    ViewToggle,
} from '@/components/common/table';
import { AlbumResponseMinimal } from '@/pythonTypes';

const STORAGE_KEY = 'library.browse.albums';
const DEFAULT_STORAGE_VALUE = {
    orderBy: 'album' as const,
    orderDirection: 'ASC' as const,
};

export const Route = createFileRoute('/library/browse/albums')({
    component: RouteComponent,
    loader: async ({ context }) => {
        const val = getStorageValue(STORAGE_KEY, DEFAULT_STORAGE_VALUE);

        await context.queryClient.ensureInfiniteQueryData(
            albumsInfiniteQueryOptions({
                ...val,
                query: '',
            })
        );
    },
});

function RouteComponent() {
    return (
        <PageWrapper
            title="Albums"
            sx={(theme) => ({
                display: 'flex',
                flexDirection: 'column',
                minHeight: '100%',
                height: '100%',
                position: 'relative',
                [theme.breakpoints.up('laptop')]: {
                    padding: 2,
                },
            })}
        >
            <BackIconButton
                sx={{
                    // TODO: styling for mobile
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    zIndex: 2,
                    margin: 0.5,
                }}
                size="small"
                color="primary"
            />
            <Box
                sx={(theme) => ({
                    height: '100%',
                    display: 'flex',
                    flexDirection: 'column',
                    overflow: 'hidden',
                    [theme.breakpoints.up('laptop')]: {
                        backgroundColor: 'background.paper',
                        borderRadius: 2,
                    },
                })}
            >
                <AlbumsHeader />
                <Divider sx={{ backgroundColor: 'primary.muted' }} />
                <View
                    sx={(theme) => ({
                        display: 'flex',
                        flexDirection: 'column',
                        height: '100%',
                        overflow: 'hidden',
                        [theme.breakpoints.down('laptop')]: {
                            background: `linear-gradient(to bottom, ${theme.palette.background.paper} 0%, transparent 100%)`,
                        },
                    })}
                />
            </Box>
        </PageWrapper>
    );
}

function AlbumsHeader({ sx, ...props }: BoxProps) {
    const theme = useTheme();
    return (
        <Box
            sx={[
                {
                    display: 'flex',
                    gap: 2,
                    alignItems: 'center',
                    padding: 2,
                },
                // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
                ...(Array.isArray(sx) ? sx : [sx]),
            ]}
            {...props}
        >
            <Box sx={{ display: 'flex', alignItems: 'center', height: '100%' }}>
                <AlbumIcon size={40} color={theme.palette.primary.main} />
            </Box>
            <Box>
                <Typography variant="h5" fontWeight="bold" lineHeight={1}>
                    Browse Albums
                </Typography>
            </Box>
        </Box>
    );
}

function View({ sx, ...props }: BoxProps) {
    const [renderStopIndex, setRenderStopIndex] = useState(0);
    const [search, setSearch] = useState('');
    const debouncedQuery = useDebounce(search, 500);

    const [view, setView] = useLocalStorage<'list' | 'grid'>(
        STORAGE_KEY + '.view',
        'list'
    );
    const [queryState, setQueryState] = useLocalStorage<{
        orderBy: 'album' | 'albumartist' | 'year';
        orderDirection: 'ASC' | 'DESC';
    }>(STORAGE_KEY + '.query', DEFAULT_STORAGE_VALUE);

    const { data, fetchNextPage, isError, isPending, isFetching, hasNextPage } =
        useInfiniteQuery(
            albumsInfiniteQueryOptions({
                query: debouncedQuery,
                orderBy: queryState.orderBy,
                orderDirection: queryState.orderDirection,
            })
        );
    const numLoaded = data?.albums.length || 0;

    // Fetch new pages on scroll
    useEffect(() => {
        if (
            renderStopIndex >= numLoaded - 10 &&
            !isFetching &&
            !isError &&
            hasNextPage
        ) {
            void fetchNextPage();
        }
    }, [
        renderStopIndex,
        numLoaded,
        fetchNextPage,
        isFetching,
        isError,
        hasNextPage,
    ]);

    return (
        <Box
            sx={[
                {
                    display: 'flex',
                    height: '100%',
                    flexDirection: 'column',
                },
                // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
                ...(Array.isArray(sx) ? sx : [sx]),
            ]}
            {...props}
        >
            {/* Header with some controls */}
            <Box
                sx={(theme) => ({
                    display: 'flex',
                    gap: 4,
                    width: '100%',
                    padding: 2,
                    [theme.breakpoints.down(500)]: {
                        flexDirection: 'column',
                        alignItems: 'flex-start',
                        gap: 2,
                    },
                })}
            >
                <Search
                    loading={isPending}
                    sx={(theme) => ({
                        mr: 'auto',
                        minHeight: 'unset',
                        height: '100%',

                        input: { height: '100%', p: 0 },
                        '.MuiInputBase-root': {
                            height: '100%',
                        },
                        [theme.breakpoints.down(500)]: {
                            width: '100%',
                            minHeight: '44px',
                        },
                    })}
                    value={search}
                    setValue={(newQuery: string) => {
                        setSearch(newQuery);
                    }}
                />
                <Box
                    sx={(theme) => ({
                        display: 'flex',
                        columnGap: 4,
                        height: '100%',
                        justifyContent: 'flex-end',
                        [theme.breakpoints.down(325)]: {
                            flexDirection: 'column',
                            alignItems: 'flex-end',
                            rowGap: 2,
                            width: '100%',
                            '> *': {
                                height: '44px',
                            },
                        },
                    })}
                >
                    <SortToggle
                        value={{
                            value: queryState.orderBy,
                            direction: queryState.orderDirection,
                        }}
                        setValue={(newSort: CurrentSort) => {
                            setQueryState({
                                ...queryState,
                                orderBy: newSort.value as
                                    'album' | 'albumartist' | 'year',
                                orderDirection: newSort.direction,
                            });
                        }}
                        items={[
                            {
                                label: 'Title',
                                value: 'album',
                            },
                            {
                                label: 'Artist',
                                value: 'albumartist',
                            },
                            {
                                label: 'Year',
                                value: 'year',
                            },
                        ]}
                    />
                    <ViewToggle view={view} setView={setView} />
                </Box>
            </Box>
            {/* table */}
            <Box
                sx={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 2,
                    height: '100%',
                }}
            >
                {view === 'grid' ? (
                    <AlbumsCoverGrid
                        data={data}
                        onCellsRendered={({ stopIndex }) => {
                            setRenderStopIndex(stopIndex);
                        }}
                    />
                ) : (
                    <AlbumsList
                        data={data}
                        onRowsRendered={({ stopIndex }) => {
                            setRenderStopIndex(stopIndex);
                        }}
                    />
                )}
                {data && data.total === 0 && !isPending && !isFetching && (
                    <Box
                        sx={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            height: '100%',
                        }}
                    >
                        <Typography variant="body1" color="text.secondary">
                            No albums found.
                        </Typography>
                    </Box>
                )}
            </Box>
        </Box>
    );
}

/* -------------------------------- grid view ------------------------------- */

function AlbumsCoverGrid({
    data,
    ...props
}: {
    onCellsRendered?: DynamicFlowGridProps['onCellsRendered'];
} & {
    data?: {
        albums: AlbumResponseMinimal[];
        total: number;
    };
}) {
    return (
        <DynamicFlowGrid
            cellProps={{ albums: data?.albums || [] }}
            cellCount={data?.total || 0}
            cellHeight={150}
            cellWidth={150}
            cellComponent={AlbumGridCell}
            overscanCount={50}
            {...props}
        />
    );
}

/* -------------------------------- list view ------------------------------- */

interface RowProps {
    albums: AlbumResponseMinimal[];
}

export function AlbumsList({
    data,
    ...props
}: {
    data?: {
        albums: AlbumResponseMinimal[];
        total: number;
    };
} & Omit<
    ListProps<RowProps>,
    'rowProps' | 'rowCount' | 'rowHeight' | 'rowComponent'
>) {
    return (
        <List
            rowProps={{ albums: data?.albums || [] }}
            rowCount={data?.total || 0}
            rowHeight={50}
            overscanCount={50}
            rowComponent={AlbumListRow}
            {...props}
        />
    );
}
