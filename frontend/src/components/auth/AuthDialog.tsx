import { UserRoundKeyIcon } from 'lucide-react';
import { useState } from 'react';
import {
    Button,
    DialogContent,
    Link,
    Stack,
    TextField,
    Typography,
} from '@mui/material';

import { useAuth } from '@/api/auth';
import { Dialog } from '@/components/common/dialogs';
import { AuthFlow } from '@/pythonTypes';

/** Modal for the PKCE flow of a single provider.
 *
 * 1. "Open login page" starts the flow and opens the provider's login URL.
 * 2. The user pastes the redirect URL they were sent to after logging in.
 * 3. "Complete" exchanges the code for a token and closes the dialog.
 */
export function AuthDialog({
    provider,
    onClose,
}: {
    provider: string;
    onClose: () => void;
}) {
    const { start, complete } = useAuth(provider);
    const [flow, setFlow] = useState<AuthFlow | null>(null);
    const [redirectUrl, setRedirectUrl] = useState('');
    const [popupBlocked, setPopupBlocked] = useState(false);

    const handleOpenLogin = () => {
        start.mutate(undefined, {
            onSuccess: (flow) => {
                setFlow(flow);
                setRedirectUrl('');
                // `noopener` makes window.open() return null when the popup is
                // blocked, in which case we offer the URL as a link instead.
                setPopupBlocked(
                    !window.open(flow.url, '_blank', 'noopener,noreferrer')
                );
            },
        });
    };

    const handleComplete = () => {
        if (!flow) return;
        complete.mutate(
            { flow_id: flow.flow_id, redirect_url: redirectUrl.trim() },
            { onSuccess: onClose }
        );
    };

    const error = start.error ?? complete.error;

    const handleClose = (
        _event: object,
        reason: 'backdropClick' | 'escapeKeyDown' | 'xIconClick'
    ) => {
        // Don't close on backdrop clicks; the in-progress flow would be lost.
        if (reason === 'backdropClick') return;
        onClose();
    };

    return (
        <Dialog
            open
            onClose={handleClose}
            title={`Authenticate ${provider}`}
            title_icon={<UserRoundKeyIcon />}
        >
            <DialogContent>
                <Stack spacing={2}>
                    <Typography variant="body2">
                        To use {provider} as a metadata source, log in with your
                        account:
                    </Typography>
                    <ol style={{ margin: 0, paddingLeft: 20 }}>
                        <li>Click &quot;Open login page&quot; below.</li>
                        <li>Log in and approve the access.</li>
                        <li>
                            You will be redirected to a page that fails to load;
                            copy the full URL from the address bar.
                        </li>
                        <li>
                            Paste it into the field below and click
                            &quot;Complete&quot;.
                        </li>
                    </ol>
                    <Button
                        variant="contained"
                        onClick={handleOpenLogin}
                        disabled={start.isPending}
                    >
                        {start.isPending ? 'Opening...' : 'Open login page'}
                    </Button>
                    <TextField
                        fullWidth
                        multiline
                        minRows={3}
                        label="Redirect URL"
                        placeholder="https://localhost/?code=...&state=..."
                        value={redirectUrl}
                        onChange={(e) => setRedirectUrl(e.target.value)}
                        disabled={complete.isPending}
                    />
                    {popupBlocked && flow && (
                        <Typography variant="body2">
                            Your browser blocked the popup. Open{' '}
                            <Link
                                href={flow.url}
                                target="_blank"
                                rel="noopener noreferrer"
                            >
                                the login page
                            </Link>{' '}
                            manually.
                        </Typography>
                    )}
                    {error && (
                        <Typography variant="body2" color="error">
                            {error.message}
                        </Typography>
                    )}
                    <Button
                        variant="contained"
                        onClick={handleComplete}
                        disabled={
                            !flow || !redirectUrl.trim() || complete.isPending
                        }
                    >
                        {complete.isPending ? 'Completing...' : 'Complete'}
                    </Button>
                </Stack>
            </DialogContent>
        </Dialog>
    );
}
