import { Alert, AlertTitle, Box } from '@mui/material';
import { createFileRoute } from '@tanstack/react-router';

import { useConfig } from '@/api/config';
import { PageWrapper } from '@/components/common/page';
import { Terminal } from '@/components/frontpage/terminal';

export const Route = createFileRoute('/terminal/')({
    component: TerminalPage,
});

function TerminalPage() {
    const config = useConfig();
    if (!config.gui.terminal.enable) {
        return (
            <Box
                display="flex"
                justifyContent="center"
                alignItems="center"
                minHeight="75vh"
            >
                <Alert severity="warning">
                    <AlertTitle>Terminal Disabled</AlertTitle>
                    <Box>
                        The terminal is not enabled in the server configuration.
                    </Box>
                </Alert>
            </Box>
        );
    }

    return (
        <PageWrapper
            sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}
        >
            <Terminal style={{ height: '100%' }} />
        </PageWrapper>
    );
}
