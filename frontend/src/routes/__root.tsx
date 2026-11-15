import { lazy, Suspense, useEffect, useState } from 'react';
import Box, { BoxProps } from '@mui/material/Box';
import { QueryClient } from '@tanstack/react-query';
import { HeadContent } from '@tanstack/react-router';
import { createRootRouteWithContext, Outlet } from '@tanstack/react-router';

import { PageWrapper } from '@/components/common/page';
import NavBar, { NAVBAR_HEIGHT } from '@/components/frontpage/navbar';
import { TerminalContextProvider } from '@/components/frontpage/terminal';
import {
    AudioContextProvider,
    useAudioContext,
} from '@/components/library/audio/context';

export const Route = createRootRouteWithContext<{
    queryClient: QueryClient;
}>()({
    component: RootComponent,
    head: () => ({
        meta: [
            {
                name: 'description',
                content:
                    'Opinionated web-interface around the music organizer beets.',
            },
            {
                title: 'Beets',
            },
        ],
        links: [
            {
                rel: 'icon',
                type: 'image/png',
                href: '/logo_beets.png',
            },
        ],
    }),
});

function RootComponent() {
    // We need to keep track of the audio player height
    // to properly allow scrolling behind it.
    const [instance, setInstance] = useState(null);
    const [audioHeight, setAudioHeight] = useState<number | null>(null);
    useEffect(() => {
        if (!instance) return;
        const playerElem = instance;
        const resizeObserver = new ResizeObserver((entries) => {
            const height = entries[0].borderBoxSize[0].blockSize;
            setAudioHeight(height);
        });
        resizeObserver.observe(playerElem);
        return () => {
            resizeObserver.unobserve(playerElem);
        };
    }, [instance]);

    return (
        <TerminalContextProvider>
            <AudioContextProvider>
                <HeadContent />
                <main
                    style={{
                        display: 'flex',
                        flexDirection: 'column',
                        height: '100dvh',
                        overflow: 'hidden',
                    }}
                >
                    <NavBar id="navbar" />
                    <Box
                        id="main-content"
                        sx={(theme) => ({
                            [theme.breakpoints.down('laptop')]: {
                                height: '100dvh',
                            },
                            width: '100%',
                            height: '100%',
                            overflow: 'visible',
                        })}
                    >
                        <Box
                            sx={(theme) => ({
                                height: '100%',
                                overflow: 'auto',

                                // includes padding for the navbar at bottom if
                                // on mobile
                                paddingBottom: `${audioHeight || 0}px`,
                                [theme.breakpoints.up('laptop')]: {
                                    paddingTop: NAVBAR_HEIGHT.desktop,
                                },
                            })}
                        >
                            <Outlet />
                        </Box>
                    </Box>
                    <LazyAudioPlayer id="audio-player" ref={setInstance} />
                </main>
            </AudioContextProvider>
        </TerminalContextProvider>
    );
}

/** We do not want to load the audio
 * player components if they are not used.
 *
 * The following allow us to lazy load the audio
 * player components.
 */
const AudioPlayer = lazy(() => import('@/components/library/audio/player'));

function LazyAudioPlayer(
    props: BoxProps,
    ref: React.Ref<HTMLDivElement> = null
) {
    const { showGlobalPlayer } = useAudioContext();

    return (
        <Suspense fallback={<Box />}>
            <Box
                ref={ref}
                sx={(theme) => ({
                    position: 'absolute',
                    bottom: 0,
                    width: '100%',
                    zIndex: 1,
                    [theme.breakpoints.down('laptop')]: {
                        paddingBottom: NAVBAR_HEIGHT.mobile,
                    },
                    [theme.breakpoints.up('laptop')]: {
                        paddingBottom: 1,
                    },
                })}
                {...props}
            >
                {
                    // Only render the audio player if there are items in the queue
                    showGlobalPlayer && (
                        <PageWrapper
                            sx={{
                                paddingInline: 1,
                            }}
                        >
                            <AudioPlayer />
                        </PageWrapper>
                    )
                }
            </Box>
        </Suspense>
    );
}
