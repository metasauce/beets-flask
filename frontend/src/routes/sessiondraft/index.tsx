import { useMemo } from 'react';
import { Box } from '@mui/material';
import { useSuspenseQuery } from '@tanstack/react-query';
import { createFileRoute } from '@tanstack/react-router';

import { walkFolder } from '@/api/inbox';
import { FolderComponent } from '@/components/sessiondraft/comps';
import { Folder } from '@/pythonTypes';

const inboxQueryOptions = () => ({
    queryKey: ['inbox'],
    queryFn: async () => {
        const response = await fetch(`/inbox/tree`);
        return (await response.json()) as Folder[];
    },
});

export const Route = createFileRoute('/sessiondraft/')({
    component: RouteComponent,
    loader: async ({ context }) => {
        await context.queryClient.ensureQueryData(inboxQueryOptions());
    },
});

function RouteComponent() {
    const { data } = useSuspenseQuery(inboxQueryOptions());
    const flat = useMemo(() => {
        const folders = [];
        for (const item of walkFolder(data[0])) {
            if (item.type === 'directory') {
                folders.push(item);
            }
        }
        return folders;
    }, [data]);

    return (
        <Box
            sx={{
                // margin: "auto",
                // display: "flex",
                // flexDirection: "column",
                // alignItems: "flex-end",
                overflowY: 'scroll',
                height: 'calc(100vh - 48px)',
                scrollSnapType: 'y proximity',
            }}
        >
            {flat.map((folder, i) => (
                <FolderComponent key={i} folder={folder as Folder} />
            ))}
        </Box>
    );
}
