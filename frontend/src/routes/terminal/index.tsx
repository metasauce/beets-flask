import { Stack, Typography } from '@mui/material';
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
            <Stack justifyContent={'center'} height={'75vh'}>
                <Typography variant={'h5'} align={'center'}>
                    The terminal is not enabled in the server configuration.
                </Typography>
            </Stack>
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
