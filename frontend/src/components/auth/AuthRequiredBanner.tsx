import { UserRoundKeyIcon } from 'lucide-react';
import { useState } from 'react';
import { Alert, AlertTitle, Box, Button, Typography } from '@mui/material';

import { useAuthProviders } from '@/api/auth';
import { AuthDialog } from '@/components/auth/AuthDialog';

/** Shown when an enabled extension requires authentication.
 *
 * Rendered at the top of the inbox index page; not page-specific though.
 */
export function AuthRequiredBanner() {
    const { data: providers, isLoading } = useAuthProviders();
    const [authProvider, setAuthProvider] = useState<string | null>(null);

    // Don't flash the banner while the providers are still loading.
    if (isLoading) {
        return null;
    }

    const missing = (providers ?? []).filter((p) => !p.authenticated);
    if (missing.length === 0) {
        return null;
    }

    return (
        <>
            <Alert
                severity="warning"
                icon={<UserRoundKeyIcon />}
                sx={{ '.MuiAlert-message': { width: '100%' } }}
            >
                <AlertTitle>Authentication required</AlertTitle>
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                    <Typography variant="body2">
                        We detected that some metadata sources do not have valid
                        credentials. Importing and tagging may fail or crash
                        while such sources are enabled. Please authenticate with
                        the following providers or disable them in your beets
                        configuration.
                    </Typography>
                    <Box
                        sx={{
                            display: 'flex',
                            flexDirection: 'column',
                            gap: 1,
                            marginTop: 1,
                            justifyContent: 'center',
                            '*': {
                                maxWidth: '400px',
                            },
                        }}
                    >
                        {missing.map((provider) => (
                            <Button
                                key={provider.name}
                                variant="outlined"
                                onClick={() => setAuthProvider(provider.name)}
                            >
                                Authenticate {provider.name}
                            </Button>
                        ))}
                    </Box>
                </Box>
            </Alert>
            {authProvider && (
                <AuthDialog
                    key={authProvider}
                    provider={authProvider}
                    onClose={() => setAuthProvider(null)}
                />
            )}
        </>
    );
}
