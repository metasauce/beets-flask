import { Inbox } from 'lucide-react';
import { Box, Divider, Grid } from '@mui/material';
import { useQuery } from '@tanstack/react-query';

import { inboxStatsQueryOptions } from '@/api/inbox';
import { Card, CardAvatar, CardContent } from '@/components/frontpage/card';
import { InboxStats } from '@/pythonTypes';

export function InboxStatsGridItems() {
    const { data, isLoading, isPending, isError, error } = useQuery(
        inboxStatsQueryOptions()
    );

    if (isError) {
        return (
            <Card>
                <CardContent>Error: {error.message}</CardContent>
            </Card>
        );
    }
    if (isPending || isLoading) {
        return (
            <Card>
                <CardContent>Loading...</CardContent>
            </Card>
        );
    }

    return (
        <>
            {data.map((stats, i) => (
                <Grid
                    size={{
                        mobile: 12,
                        tablet: 8,
                        laptop: 8,
                        desktop: 6,
                    }}
                    key={i}
                >
                    <InboxCardView stats={stats} />
                </Grid>
            ))}
        </>
    );
}

function InboxCardView({ stats }: { stats: InboxStats }) {
    return (
        <Card>
            <CardContent>
                <CardAvatar Icon={Inbox} title={stats.name}>
                    <Box
                        component="code"
                        sx={{
                            fontSize: 14,
                            color: 'grey.500',
                            marginBottom: '0.875em',
                        }}
                    >
                        {stats.path}
                    </Box>
                </CardAvatar>

                <div className="h-full flex flex-col justify-end">
                    <InboxTable stats={stats} />
                </div>
            </CardContent>
            <Divider className="mt-auto" />
        </Card>
    );
}

function InboxTable({ stats }: { stats: InboxStats }) {
    const files = stats.nFiles ?? 0;
    const size = stats.size;

    return (
        <table className="table-info text-gray-100 text-sm">
            <thead>
                <tr>
                    <th>
                        <span>Untagged</span>
                    </th>
                    <th>
                        <span>Tagged</span>
                    </th>
                    <th>Total</th>
                    <th></th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>{files}</td>
                    <td>files</td>
                </tr>
                <tr>
                    <td>
                        {size === null
                            ? 'unknown'
                            : Math.round(size / 1024 / 1024)}
                    </td>
                    <td>{size === null ? '' : 'mb'}</td>
                </tr>
            </tbody>
        </table>
    );
}
