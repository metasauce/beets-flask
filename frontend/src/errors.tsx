import { ChevronDownIcon, ChevronUpIcon } from 'lucide-react';
import { useEffect, useState } from 'react';
import {
    Avatar,
    Button,
    CardHeader,
    Divider,
    Paper,
    useTheme,
} from '@mui/material';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardActions from '@mui/material/CardActions';
import CardContent from '@mui/material/CardContent';
import CardMedia from '@mui/material/CardMedia';
import Link from '@mui/material/Link';
import Typography from '@mui/material/Typography';
import { useRouter } from '@tanstack/react-router';

import { BackButton } from './components/common/inputs/back';
import { SerializedException } from './pythonTypes';

import brokenRecord from '@/assets/broken-record.png';

/** Default component for showing errors
 * Hopefully this should not happen, but they
 * are also useful for debugging.
 *
 * This basically shows a card with the error message
 * and the stack trace.
 *
 * Also includes a link to the github issues page.
 */
export function ErrorCard({ error }: { error: Error }) {
    useEffect(() => {
        console.error(error);
    }, [error]);

    return (
        <GenericErrorCard
            title="Unexpected Error"
            subtitle="Oh no! Seems like we dropped a beat!"
            color="primary"
            exc={{
                type: error.name,
                message: error.message,
                description: error.message,
                trace: error.stack,
            }}
            showSocials={true}
        />
    );
}

export function GenericErrorCard({
    title,
    subtitle,
    color,
    exc,
    showSocials = false,
}: {
    title: string;
    subtitle: string;
    color: 'primary' | 'secondary';
    exc: SerializedException;
    showSocials?: boolean;
}) {
    const theme = useTheme();
    const router = useRouter();
    const [showDetails, setShowDetails] = useState(false);

    return (
        <Card elevation={3} sx={{ width: '100%' }}>
            {/* Card Header */}
            <CardHeader
                avatar={
                    <Avatar
                        sx={{
                            bgcolor: `${color}.muted`,
                            width: 60,
                            height: 60,
                        }}
                    >
                        <CardMedia
                            component="img"
                            image={brokenRecord}
                            sx={{
                                height: 'auto',
                                objectFit: 'contain',
                            }}
                            title="broken record"
                        />
                    </Avatar>
                }
                title={
                    <Typography variant="h5" fontWeight="bold">
                        {title}
                    </Typography>
                }
                subheader={subtitle}
                sx={{
                    pb: 3,
                    borderBottom: '1px solid',
                    borderColor: 'divider',
                    '& .MuiCardHeader-subheader': {
                        color: 'text.secondary',
                    },
                }}
            />
            <CardContent sx={{ pt: 3, overflow: 'auto' }}>
                <Box sx={{ mb: 3 }}>
                    <Typography
                        variant="body2"
                        color="text.secondary"
                        gutterBottom
                    >
                        Error Type
                    </Typography>
                    <Paper
                        variant="outlined"
                        sx={{ p: 1.5, bgcolor: '#0a0a0a' }}
                    >
                        <Typography variant="body1" fontFamily="monospace">
                            {exc.type}
                        </Typography>
                    </Paper>
                </Box>

                <Box sx={{ mb: 3 }}>
                    <Typography
                        variant="body2"
                        color="text.secondary"
                        gutterBottom
                    >
                        Message
                    </Typography>
                    <Paper
                        variant="outlined"
                        sx={{ p: 1.5, bgcolor: '#0a0a0a' }}
                    >
                        <Typography variant="body1" fontFamily="monospace">
                            {exc.message}
                        </Typography>
                    </Paper>
                </Box>

                {showDetails && (
                    <>
                        <Box sx={{ mb: 1 }}>
                            <Typography
                                variant="body2"
                                color="text.secondary"
                                gutterBottom
                            >
                                Description
                            </Typography>
                            <Paper
                                variant="outlined"
                                sx={{
                                    p: 1.5,
                                    bgcolor: '#0a0a0a',
                                    overflowX: 'auto',
                                }}
                            >
                                <Typography
                                    variant="body2"
                                    fontFamily="monospace"
                                >
                                    {exc.description ||
                                        'No description available'}
                                </Typography>
                            </Paper>
                        </Box>
                        <Box sx={{ mb: 1 }}>
                            <Typography
                                variant="body2"
                                color="text.secondary"
                                gutterBottom
                            >
                                Stack Trace
                            </Typography>
                            <Paper
                                variant="outlined"
                                sx={{
                                    p: 1.5,
                                    bgcolor: '#0a0a0a',
                                    overflowX: 'auto',
                                }}
                            >
                                <Typography
                                    variant="body2"
                                    fontFamily="monospace"
                                >
                                    <pre>
                                        {exc.trace ||
                                            'No stack trace available'}
                                    </pre>
                                </Typography>
                            </Paper>
                        </Box>
                    </>
                )}

                {showSocials && (
                    <Typography
                        variant="body2"
                        sx={{ color: 'text.secondary', marginTop: '0.2rem' }}
                    >
                        If this is a reoccurring issue, feel free to raise an{' '}
                        <Link href="https://github.com/metasauce/beets-flask/issues">
                            issue on GitHub
                        </Link>
                        .
                    </Typography>
                )}
            </CardContent>

            <Divider />

            <CardActions sx={{ justifyContent: 'space-between', p: 2 }}>
                <Button
                    variant="outlined"
                    onClick={() => setShowDetails(!showDetails)}
                    startIcon={
                        showDetails ? (
                            <ChevronDownIcon size={theme.iconSize.sm} />
                        ) : (
                            <ChevronUpIcon size={theme.iconSize.sm} />
                        )
                    }
                    size="small"
                    color={color}
                >
                    {showDetails ? 'Hide Details' : 'Show Details'}
                </Button>
                <Box sx={{ display: 'flex', gap: 1, ml: 'auto' }}>
                    <BackButton
                        variant="outlined"
                        color={color}
                        sx={{ mr: 1 }}
                    />
                    <Button
                        variant="contained"
                        color={color}
                        size="small"
                        onClick={async () => {
                            await router.invalidate();
                        }}
                    >
                        Retry
                    </Button>
                </Box>
            </CardActions>
        </Card>
    );
}
