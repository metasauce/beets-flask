import { BookOpenIcon, BugIcon } from 'lucide-react';
import { Box, Link, Typography, useTheme } from '@mui/material';
import { useSuspenseQuery } from '@tanstack/react-query';
import { createFileRoute } from '@tanstack/react-router';

import { inboxStatsQueryOptions } from '@/api/inbox';
import { libraryStatsQueryOptions } from '@/api/library';
import { GithubIcon } from '@/components/common/icons';
import { Link as InternalLink } from '@/components/common/link';
import { PageWrapper } from '@/components/common/page';
import {
    InboxStatsCard,
    LibraryStatsCard,
} from '@/components/frontpage/statsCard';

/* ------------------------------ Route layout ------------------------------ */

export const Route = createFileRoute('/_frontpage/')({
    component: Index,
    loader: async ({ context }) => {
        return await Promise.all([
            context.queryClient.ensureQueryData(libraryStatsQueryOptions()),
            context.queryClient.ensureQueryData(inboxStatsQueryOptions()),
        ]);
    },
    staleTime: 20_000, // 20 seconds
});

/** The frontpage is layout which adds an overview
 * of the current inbox, displaying the number of files,
 * the size, the number of tagged files, the size of tagged.
 * Also some redis stats are shown.
 *
 * It also gives an outlet to render other relevant content
 * underneath. This may also be used to render a modal.
 */
function Index() {
    const { data: inboxStats } = useSuspenseQuery(inboxStatsQueryOptions());
    const { data: libraryStats } = useSuspenseQuery(libraryStatsQueryOptions());

    return (
        <PageWrapper
            sx={(theme) => ({
                paddingTop: 2,
                minHeight: '100%',
                display: 'flex',
                flexDirection: 'column',
                gap: 6,
                maxWidth: `${theme.breakpoints.values.laptop}px !important`,
            })}
        >
            <Hero />
            <Box
                sx={{
                    display: 'flex',
                    gap: 5,
                    flexDirection: 'column',
                    paddingInline: 1,
                }}
            >
                <LibraryStatsCard libraryStats={libraryStats} />
                {inboxStats.map((inbox, i) => (
                    <InboxStatsCard inboxStats={inbox} key={i} />
                ))}
            </Box>
            <Footer />
        </PageWrapper>
    );
}

/* ------------------------------- Hero section ----------------------------- */

function Hero() {
    // Readme: Breakpoints are set to align with the font
    // and size of the logo. Using the set breakpoints for
    // different devices will not work as expected here
    return (
        <Box sx={{ margin: '0 auto' }}>
            <Box
                sx={{
                    display: 'grid',
                    gridTemplateColumns: 'min-content auto',
                    columnGap: 2,
                    justifyContent: 'center',

                    '@media (max-width: 500px)': {
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                    },
                }}
            >
                <Box
                    component="img"
                    src="/logo_flask.png"
                    alt="Logo"
                    sx={{
                        width: '150px',
                        height: '150px',
                        gridRow: 'span 2',
                        gridColumn: '1',
                        '@media (max-width: 890px)': {
                            gridRow: '1',
                            gridColumn: '1',
                        },
                    }}
                />
                <Typography
                    component="h1"
                    variant="h2"
                    sx={{
                        fontSize: 64,
                        alignSelf: 'flex-end',
                        '@media (max-width: 500px)': {
                            alignSelf: 'center',
                        },
                    }}
                    fontWeight={600}
                >
                    Beets-flask
                </Typography>
                <Box
                    sx={{
                        gridRow: '2',
                        gridColumn: '2',
                        '@media (max-width: 890px)': {
                            gridRow: '2',
                            gridColumn: 'span 2',
                            paddingTop: 1,
                            paddingLeft: 2,
                            paddingRight: 1,
                        },
                        width: '100%',
                    }}
                >
                    <Typography
                        component="h2"
                        variant="h6"
                        sx={{
                            color: 'grey.500',
                            '@media (max-width: 890px)': {
                                textAlign: 'center',
                                width: '100%',
                            },
                        }}
                    >
                        Web interface around your favorite music tagger and
                        music library.
                    </Typography>
                </Box>
            </Box>
        </Box>
    );
}

/* ------------------------------ Footer section ---------------------------- */

export function VersionString() {
    let versionString = `v${__FRONTEND_VERSION__}`;
    if (__MODE__ !== 'production') {
        // Append the mode to the version string if not in production
        versionString += ` (${__MODE__})`;
    }
    return versionString;
}

function Footer() {
    const theme = useTheme();

    return (
        <Box
            sx={(theme) => ({
                paddingTop: 3,
                paddingBottom: 1,
                paddingInline: 1,
                display: 'flex',
                gap: 2,
                marginTop: 'auto',
                justifyContent: 'flex-end',
                alignItems: 'flex-end',
                // do not show spans with text on mobile
                [theme.breakpoints.down('tablet')]: {
                    '>*>span': {
                        display: 'none',
                    },
                },
                a: {
                    display: 'flex',
                    alignItems: 'flex-end',
                },
            })}
        >
            <InternalLink
                to="/version"
                sx={{ textDecoration: 'none', mr: 'auto' }}
            >
                <Typography
                    variant="caption"
                    sx={{ color: 'grey.700', alignSelf: 'flex-end' }}
                >
                    <VersionString /> &copy; 2025 P. Spitzner &amp; S. Mohr
                </Typography>
            </InternalLink>

            <Link
                href="https://beets-flask.readthedocs.io/en/latest/"
                target="_blank"
                variant="body2"
            >
                <BookOpenIcon size={theme.iconSize.lg} />
                <Typography variant="caption">&nbsp;Documentation</Typography>
            </Link>
            <Link
                href="https://github.com/pSpitzner/beets-flask"
                target="_blank"
                variant="body2"
            >
                <GithubIcon size={theme.iconSize.lg} />
                <Typography variant="caption">&nbsp;GitHub</Typography>
            </Link>
            <Link
                href="https://github.com/pSpitzner/beets-flask/issues/new"
                target="_blank"
                variant="body2"
            >
                <BugIcon size={theme.iconSize.lg} />
                <Typography variant="caption">&nbsp;Report a bug</Typography>
            </Link>
        </Box>
    );
}
