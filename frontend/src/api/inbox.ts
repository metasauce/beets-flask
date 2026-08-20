/** Includes function to interact with
 * our backend API for the inbox i.e.
 *
 * /api_v1/inbox
 */

import { UseMutationOptions } from '@tanstack/react-query';

import type { FileSystemItem, Folder, InboxStats } from '@/pythonTypes';

import { APIError, queryClient } from './common';

// Tree of inbox folders
// Only refetches when explicitly invalidated (file system updates via the
// socket, or the manual refresh below); the tree itself is static otherwise.
export const inboxQueryOptions = () => ({
    queryKey: ['inbox'],
    staleTime: Infinity,
    queryFn: async () => {
        const response = await fetch(`/inbox/tree`);
        return (await response.json()) as Folder[];
    },
});

/** Reset cache of the tree
 * needed for manual refresh.
 */
queryClient.setMutationDefaults(['refreshInboxTree'], {
    mutationFn: async () => {
        await fetch(`/inbox/tree/refresh`, { method: 'POST' });
    },
    onSuccess: async () => {
        // Invalidate the query after the cache has been reset
        const q = inboxQueryOptions();

        // At least 0.5 second delay for loading indicator
        const ps = [
            queryClient
                .cancelQueries(q)
                .then(() => queryClient.invalidateQueries(q)),
            new Promise((resolve) => setTimeout(resolve, 500)),
        ];
        await Promise.all(ps);
    },
});

// A specific folder
// Same staleness contract as the inbox tree: only refetches when the
// `['inbox']` key is invalidated (file system updates or manual refresh).
export const inboxFolderQueryOptions = (path: string, hash?: string) => ({
    queryKey: [
        'inbox',
        {
            path,
            hash,
        },
    ],
    staleTime: Infinity,
    queryFn: async () => {
        const response = await fetch(`/inbox/folder`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                folder_paths: [path],
                folder_hashes: hash ? [hash] : [],
            }),
        });
        return (await response.json()) as Folder;
    },
});

// Some stats about the inbox(es)
export const inboxStatsQueryOptions = () => ({
    queryKey: ['inbox', 'stats'],
    staleTime: Infinity,
    queryFn: async () => {
        const response = await fetch(`/inbox/stats`);
        const dat = (await response.json()) as InboxStats[];
        dat.forEach((d) => {
            d.last_created = d.last_created ? new Date(d.last_created) : null;
        });
        return dat;
    },
});

/* -------------------------------- Mutations ------------------------------- */
// Here for reference, not used yet but we might need it in the future

export const deleteFoldersMutationOptions: UseMutationOptions<
    Response | undefined,
    APIError,
    {
        folderPaths: string[];
        folderHashes: string[];
    },
    {
        previousInbox: Folder[] | undefined;
    }
> = {
    mutationFn: async ({ folderPaths, folderHashes }) => {
        return await fetch(`/inbox/delete`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                folder_paths: folderPaths,
                folder_hashes: folderHashes,
            }),
        });
    },

    // Optimistic update
    onMutate: async ({ folderPaths, folderHashes }) => {
        // Cancel any outgoing refetches (so they don't overwrite our optimistic update)
        await queryClient.cancelQueries({ queryKey: ['inbox'] });
        // Snapshot the previous value
        const previousInbox = queryClient.getQueryData<Folder[]>(['inbox']);
        // Optimistically update to the new value
        queryClient.setQueryData<Folder[]>(['inbox'], (old) => {
            if (!old) return old;
            // needs structured clone to trigger the rerender and avoid setstate issues
            const new_folders = structuredClone(old);
            deleteFromFolder(folderHashes, folderPaths, new_folders);
            return new_folders;
        });
        // Return a context object with the snapshotted value
        return { previousInbox };
    },
    onError: (_err, _variables, context) => {
        // If the mutation fails, use the context returned from onMutate
        queryClient.setQueryData(['inbox'], context?.previousInbox);
    },

    // If the mutation is successful, invalidate the query, this should trigger a refetch
    onSettled: async () => {
        await queryClient.invalidateQueries({ queryKey: ['inbox'] });
    },
};

function deleteFromFolder(
    hashes: string[],
    paths: string[],
    folders: FileSystemItem[]
) {
    // break recursion
    if (folders.length === 0) {
        return;
    }

    // delete children if matches
    for (let i = 0; i < folders.length; i++) {
        const f = folders[i];
        if (
            f.type === 'directory' &&
            (hashes.includes(f.hash) || paths.includes(f.full_path))
        ) {
            folders.splice(i, 1);
            i--;
        } else if (f.type === 'directory') {
            deleteFromFolder(hashes, paths, (f as Folder).children);
        }
    }
}

/**
 * Depth-first walk over a folder tree.
 *
 * @param folder The root folder to walk.
 * @param depth How many directory levels to descend into. `0` yields only
 *              the root folder, `1` yields the root and its immediate
 *              children, etc. Defaults to `Infinity` (full walk).
 */
export function* walkFolder(
    folder: Folder,
    depth: number = Infinity
): Generator<FileSystemItem> {
    yield folder;
    if (depth <= 0) {
        return;
    }
    for (const child of folder.children) {
        if (child.type === 'directory') {
            yield* walkFolder(child as Folder, depth - 1);
        } else {
            yield child;
        }
    }
}
