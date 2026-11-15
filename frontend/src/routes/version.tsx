import { ChevronDownIcon } from 'lucide-react';
import {
    AccordionDetails,
    AccordionSummary,
    Box,
    Divider,
    Paper,
    Typography,
    useTheme,
} from '@mui/material';
import { Accordion } from '@mui/material';
import { useSuspenseQuery } from '@tanstack/react-query';
import { createFileRoute } from '@tanstack/react-router';

import { configYamlQueryOptions, useConfig } from '@/api/config';
import { SourceTypeIcon } from '@/components/common/icons';
import { PageWrapper } from '@/components/common/page';

import { VersionString } from './_frontpage';

export const Route = createFileRoute('/version')({
    component: RouteComponent,
});

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
                <Accordion
                    disableGutters
                    sx={{
                        boxShadow: 'none',
                        border: 'none',
                        outline: 'none',
                        '::before': { backgroundColor: 'unset' },
                        '.MuiAccordionSummary-content': {
                            padding: 0,
                            margin: 0,
                        },
                        button: {
                            height: 'auto',
                            padding: 0,
                            display: 'flex',
                            alignItems: 'flex-start',
                            minHeight: 'auto',
                        },
                    }}
                >
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
                <Accordion
                    disableGutters
                    sx={{
                        boxShadow: 'none',
                        border: 'none',
                        outline: 'none',
                        '::before': { backgroundColor: 'unset' },
                        '.MuiAccordionSummary-content': {
                            padding: 0,
                            margin: 0,
                        },
                        button: {
                            height: 'auto',
                            padding: 0,
                            display: 'flex',
                            alignItems: 'flex-start',
                            minHeight: 'auto',
                        },
                    }}
                >
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
