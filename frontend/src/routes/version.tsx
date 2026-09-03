import { ChevronDownIcon } from 'lucide-react';
import { lazy, Suspense, useState } from 'react';
import {
    AccordionDetails,
    AccordionSummary,
    Box,
    Button,
    Divider,
    Paper,
    Typography,
    useTheme,
} from '@mui/material';
import { Accordion } from '@mui/material';
import { useSuspenseQuery } from '@tanstack/react-query';
import { createFileRoute } from '@tanstack/react-router';

import { authProvidersQueryOptions } from '@/api/auth';
import { configYamlQueryOptions, useConfig } from '@/api/config';
import { SourceTypeIcon } from '@/components/common/icons';
import { PageWrapper } from '@/components/common/page';
import { AuthProviderStatus } from '@/pythonTypes';

import { VersionString } from './_frontpage';

/** Lazily loaded so the dialog chunk is only fetched when first opened. */
const AuthDialog = lazy(() =>
    import('@/components/auth/AuthDialog').then((m) => ({
        default: m.AuthDialog,
    }))
);

export const Route = createFileRoute('/version')({
    component: RouteComponent,
});

/** Shared styling so all accordions on this page look alike. */
const accordionSx = {
    boxShadow: 'none',
    border: 'none',
    outline: 'none',
    '::before': { backgroundColor: 'unset' },
    '.MuiAccordionSummary-content': {
        padding: 0,
        margin: 0,
    },
    '.MuiAccordionSummary-root': {
        height: 'auto',
        padding: 0,
        display: 'flex',
        alignItems: 'flex-start',
        minHeight: 'auto',
    },
};

/** A relative simple page showing the current version */
function RouteComponent() {
    return (
        <PageWrapper>
            <Paper
                elevation={3}
                sx={{
                    padding: 2,
                    margin: 2,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 2,
                    justifyContent: 'center',
                }}
            >
                <Box sx={{ marginBottom: 2 }}>
                    <Typography component="h1" variant="h4" gutterBottom>
                        Version Info
                    </Typography>
                    <Typography
                        variant="body1"
                        gutterBottom
                        sx={{
                            display: 'flex',
                            gap: 1,
                            maxWidth: '600px',
                        }}
                    >
                        Looks like your found our debug page. You can find some
                        relevant information about the current installation
                        here. This may be useful when reporting bugs or issues.
                    </Typography>
                </Box>
                <Divider />
                <Box
                    sx={{
                        display: 'grid',
                        gap: 1,
                        columnGap: 2,
                        gridTemplateColumns: 'auto 1fr',
                    }}
                >
                    <Version />
                    <DataSources />
                    <Plugins />
                    <Extensions />
                    <Config />
                </Box>
            </Paper>
        </PageWrapper>
    );
}

function Version() {
    const config = useConfig();

    return (
        <>
            <Typography
                component="label"
                variant="caption"
                fontWeight="bold"
                color="textSecondary"
            >
                Version
            </Typography>
            <Box display="flex" flexDirection="column">
                <Typography
                    component="span"
                    fontFamily="monospace"
                    variant="body1"
                >
                    beets-flask: <VersionString />
                </Typography>
                <Typography
                    component="span"
                    fontFamily="monospace"
                    variant="body1"
                    sx={{ display: 'flex', alignItems: 'center', gap: 1 }}
                >
                    beets: {config.beets_version}
                </Typography>
            </Box>
        </>
    );
}

function DataSources() {
    const theme = useTheme();
    const config = useConfig();

    return (
        <>
            <Typography
                component="label"
                variant="caption"
                fontWeight="bold"
                color="textSecondary"
            >
                Data Sources
            </Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
                {config.beets_metadata_sources.map((source) => (
                    <Box
                        key={source}
                        sx={{ display: 'flex', gap: 1, alignItems: 'center' }}
                    >
                        <Typography
                            variant="body1"
                            component="span"
                            fontFamily="monospace"
                        >
                            {source.toLowerCase()}
                        </Typography>
                        <SourceTypeIcon
                            type={source}
                            size={theme.iconSize.sm}
                        />
                    </Box>
                ))}
            </Box>
        </>
    );
}

function Plugins() {
    const config = useConfig();

    return (
        <>
            <Typography
                component="label"
                variant="caption"
                fontWeight="bold"
                color="textSecondary"
            >
                Plugins
            </Typography>
            <Box sx={{ display: 'flex', flexDirection: 'column' }}>
                {config.plugins.map((plugin) => (
                    <Box
                        key={plugin}
                        sx={{ display: 'flex', gap: 1, alignItems: 'center' }}
                    >
                        <Typography
                            variant="body1"
                            component="span"
                            fontFamily="monospace"
                        >
                            {plugin}
                        </Typography>
                    </Box>
                ))}
            </Box>
        </>
    );
}

/** Section listing enabled beets-flask extensions. */
function Extensions() {
    return (
        <>
            <Typography
                component="label"
                variant="caption"
                fontWeight="bold"
                color="textSecondary"
            >
                Extensions
            </Typography>
            <Box
                sx={{
                    display: 'flex',
                    flexDirection: 'column',
                    maxWidth: '100%',
                    overflow: 'hidden',
                    gap: 1,
                }}
            >
                <Accordion disableGutters sx={accordionSx}>
                    <AccordionSummary expandIcon={<ChevronDownIcon />}>
                        <Typography fontFamily="monospace">Auth</Typography>
                    </AccordionSummary>
                    <AccordionDetails>
                        <AuthExtensions />
                    </AccordionDetails>
                </Accordion>
            </Box>
        </>
    );
}

/** Auth extensions content: per-provider status with (re-)authentication. */
function AuthExtensions() {
    const { data: providers } = useSuspenseQuery(authProvidersQueryOptions());

    return (
        <Box sx={{ display: 'flex', flexDirection: 'column' }}>
            {providers.length === 0 ? (
                <Typography
                    variant="body1"
                    component="span"
                    fontFamily="monospace"
                >
                    none enabled
                </Typography>
            ) : (
                providers.map((provider) => (
                    <AuthProviderRow key={provider.name} provider={provider} />
                ))
            )}
        </Box>
    );
}

/** A single auth provider row: name, status and a (re-)auth button. */
function AuthProviderRow({ provider }: { provider: AuthProviderStatus }) {
    const [open, setOpen] = useState(false);

    return (
        <>
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                <Typography
                    variant="body1"
                    component="span"
                    fontFamily="monospace"
                >
                    {provider.name}
                </Typography>
                <Typography
                    variant="body1"
                    component="span"
                    color={provider.authenticated ? 'success' : 'error'}
                >
                    {provider.authenticated
                        ? 'authenticated'
                        : 'not authenticated'}
                </Typography>
                <Button
                    size="small"
                    sx={{ ml: 'auto' }}
                    onClick={() => setOpen(true)}
                >
                    {provider.authenticated
                        ? 'Re-authenticate'
                        : 'Authenticate'}
                </Button>
            </Box>
            {open && (
                <Suspense fallback={null}>
                    <AuthDialog
                        provider={provider.name}
                        onClose={() => setOpen(false)}
                    />
                </Suspense>
            )}
        </>
    );
}

function Config() {
    const theme = useTheme();

    const { data: beetsConfigYaml } = useSuspenseQuery(
        configYamlQueryOptions('beets')
    );
    const { data: beetsflaskConfigYaml } = useSuspenseQuery(
        configYamlQueryOptions('beetsflask')
    );
    return (
        <>
            <Typography
                component="label"
                variant="caption"
                fontWeight="bold"
                color="textSecondary"
            >
                Config
            </Typography>
            <Box
                sx={{
                    display: 'flex',
                    flexDirection: 'column',
                    maxWidth: '100%',
                    overflow: 'hidden',
                    gap: 1,
                }}
            >
                <Accordion disableGutters sx={accordionSx}>
                    <AccordionSummary expandIcon={<ChevronDownIcon />}>
                        <Typography fontFamily="monospace">
                            Beets configuration
                        </Typography>
                    </AccordionSummary>
                    <AccordionDetails>
                        <Typography
                            component="span"
                            sx={{
                                backgroundColor: theme.palette.background.paper,
                                borderRadius: 1,
                                overflowX: 'auto',
                                fontFamily: 'monospace',
                                fontSize: '0.875rem',
                                whiteSpace: 'pre-wrap',
                                wordBreak: 'break-all',
                            }}
                        >
                            <pre>{beetsConfigYaml.content}</pre>
                        </Typography>
                    </AccordionDetails>
                </Accordion>
                <Accordion disableGutters sx={accordionSx}>
                    <AccordionSummary expandIcon={<ChevronDownIcon />} sx={{}}>
                        <Typography fontFamily="monospace">
                            Beets Flask configuration
                        </Typography>
                    </AccordionSummary>
                    <AccordionDetails>
                        <Typography
                            component="span"
                            sx={{
                                backgroundColor: theme.palette.background.paper,
                                borderRadius: 1,
                                overflowX: 'auto',
                                fontFamily: 'monospace',
                                fontSize: '0.875rem',
                                whiteSpace: 'pre-wrap',
                                wordBreak: 'break-all',
                            }}
                        >
                            <pre>{beetsflaskConfigYaml.content}</pre>
                        </Typography>
                    </AccordionDetails>
                </Accordion>
            </Box>
        </>
    );
}
