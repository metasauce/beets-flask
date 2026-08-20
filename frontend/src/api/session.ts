import { Query, useMutation, UseMutationOptions } from '@tanstack/react-query';

import { useStatusSocket } from '@/components/common/websocket/status';
import { DuplicateAction } from '@/components/import/candidates/actions';
import { FolderSelectionContext } from '@/components/inbox/folderSelectionContext';
import {
    CandidateChoiceFallback,
    EnqueueKind,
    FolderStatus,
    FolderStatusUpdate,
    JobStatusUpdate,
    MinimalSession,
    Search,
    SerializedCandidateState,
    SerializedException,
    SerializedSessionState,
    SerializedTaskState,
} from '@/pythonTypes';

import { APIError, queryClient } from './common';
import { StatusSocket } from './websocket';

export const sessionQueryOptions = ({
    folderHash,
    folderPath,
}: {
    folderHash: string;
    folderPath?: string;
}) => ({
    queryKey: ['session', folderHash, 'full'],
    StaleTime: Infinity,
    queryFn: async () => {
        const params = new URLSearchParams();
        params.append('folder_hash', folderHash);
        if (folderPath) {
            params.append('folder_path', folderPath);
        }
        const response = await fetch(`/session/full?${params.toString()}`);
        // make sure we have a folder
        const res = (await response.json()) as
            SerializedSessionState | SerializedException;
        // check if we have error as a key in res
        if ('type' in res) {
            // if we have an error, throw it
            throw new APIError(res);
        }

        // Parse dates as they are returned as strings
        res.created_at = new Date(res.created_at);
        res.updated_at = new Date(res.updated_at);
        for (const task of res.tasks) {
            task.created_at = new Date(task.created_at);
            task.updated_at = new Date(task.updated_at);

            for (const cand of task.candidates) {
                cand.created_at = new Date(cand.created_at);
                cand.updated_at = new Date(cand.updated_at);
            }

            // Sort candidates by score
            task.candidates = task.candidates.sort((a, b) => {
                if (a.info.data_source === 'asis') return -1;
                if (b.info.data_source === 'asis') return 1;
                return a.distance - b.distance;
            });
        }

        queryClient.setQueryData<SerializedSessionState>(
            ['session', res.folder_hash, 'full'],
            res
        );

        return res;
    },
});

/* ------------------------------ Invalidation ------------------------------ */

/** Invalidates the cached full session state and minimal chip info for a
 * given folder hash. Without a hash, invalidates all session data.
 *
 * Status entries are intentionally excluded: they are updated directly from
 * socket events (see statusQueryOptions).
 */
export async function invalidateSession(folderHash?: string): Promise<void> {
    console.debug('Invalidate session', folderHash);
    if (!folderHash) {
        await queryClient.invalidateQueries({ queryKey: ['session'] });
        return;
    }
    await Promise.all([
        queryClient.invalidateQueries({
            queryKey: ['session', folderHash, 'full'],
        }),
        queryClient.invalidateQueries({
            queryKey: ['session', folderHash, 'minimal'],
        }),
    ]);
}

/* -------------------------------- Mutations ------------------------------- */

// see related invoker/enqueue.py functions for more details
// this does not automatically come from py2ts, but we want certain
// parameters that are allowed depending on the kind
type TaskIdMap<T> = {
    [key: SerializedTaskState['id']]: T;
};

interface EnqueuePreviewAddCandidate {
    kind: EnqueueKind.PREVIEW_ADD_CANDIDATES;
    search: TaskIdMap<Search>;
}

interface EnqueuePreview {
    kind: EnqueueKind.PREVIEW;
    group_albums?: boolean;
    autotag?: boolean;
}

interface EnqueueImportCandidate {
    kind: EnqueueKind.IMPORT_CANDIDATE;
    candidate_ids?: TaskIdMap<string | CandidateChoiceFallback>;
    duplicate_actions?: TaskIdMap<DuplicateAction>;
}

interface EnqueueImportBootleg {
    kind: EnqueueKind.IMPORT_BOOTLEG;
}

interface EnqueueImportUndo {
    kind: EnqueueKind.IMPORT_UNDO;
    delete_files?: boolean;
}

export type EnqueueParams =
    | EnqueuePreviewAddCandidate
    | EnqueuePreview
    | EnqueueImportCandidate
    | EnqueueImportBootleg
    | EnqueueImportUndo;

/** Enqueue a new task
 * i.e. tag a folder of import a folder
 *
 * We have one entrypoint for invoking session
 * actions in the backend.
 */
export const enqueueMutationOptions: UseMutationOptions<
    JobStatusUpdate[],
    Error,
    {
        socket: StatusSocket | null;
        selected: FolderSelectionContext['selected'];
    } & EnqueueParams
> = {
    mutationFn: async ({ socket, selected, kind, ...extra }) => {
        if (!selected || selected.hashes.length === 0) {
            return [];
        }
        // Generate a unique job reference for each folder
        // to avoid collisions
        const jobRefs = [];
        for (const hash of selected.hashes) {
            jobRefs.push(`${hash}-${Date.now()}-${Math.random()}`);
        }

        const promiseResult = waitForJobUpdate({
            socket: socket,
            jobRef: jobRefs,
        });

        const res = await fetch('/session/enqueue', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                kind: kind.toString(),
                folder_hashes: selected.hashes,
                folder_paths: selected.paths,
                job_frontend_refs: jobRefs,
                ...extra,
            }),
        });

        // no need to process, just for debugging, errors handled in custom fetch
        const _data = (await res.json()) as JobStatusUpdate;

        // Wait for the job to finish
        return await promiseResult;
    },
    // Optimistic update for status, show pending before backend response
    onMutate: async ({ selected }) => {
        for (const [idx, hash] of selected.hashes.entries()) {
            const queryKey = statusQueryOptions(
                hash,
                selected.paths[idx]
            ).queryKey;
            await queryClient.cancelQueries({ queryKey });
            queryClient.setQueryData<FolderStatusUpdate>(queryKey, {
                path: selected.paths[idx],
                hash: hash,
                status: FolderStatus.PENDING,
                exc: null,
                event: 'folder_status_update',
            });
        }
    },
    // Fetch new session on success
    onSuccess: async (_data, { selected }) => {
        const predicate = (query: Query) => {
            if (query.queryKey[0] == 'artists') return true;
            if (query.queryKey[0] !== 'session') return false;
            // Covers 'full' and 'minimal' entries for a folder hash.
            // 'status' is updated directly via the socket, not refetched here.
            return (
                query.queryKey[2] !== 'status' &&
                selected.hashes.includes(query.queryKey[1] as string)
            );
        };

        const ps = [
            queryClient
                .cancelQueries({
                    predicate,
                })
                .then(() =>
                    queryClient.invalidateQueries({
                        predicate,
                    })
                ),
            // For loading spinner
            new Promise((resolve) => setTimeout(resolve, 500)),
        ];
        await Promise.all(ps);
    },
    onError: (_error, _variables, _context) => {
        console.error('Enqueue mutation failed', _error);
    },
};

export const useImportMutation = (
    session: SerializedSessionState,
    selectedCandidateIds: Map<
        SerializedTaskState['id'],
        SerializedCandidateState['id']
    >,
    duplicateActions: Map<SerializedTaskState['id'], DuplicateAction>
) => {
    const { socket } = useStatusSocket();
    const { mutate, mutateAsync, ...props } = useMutation(
        enqueueMutationOptions
    );

    return {
        ...props,
        mutate: () => {
            const taskIdMap: TaskIdMap<string | CandidateChoiceFallback> = {};
            const taskIdMapDuplicateActions: TaskIdMap<DuplicateAction> = {};

            for (const [taskId, candidateId] of selectedCandidateIds) {
                taskIdMap[taskId] = candidateId;
            }
            for (const [taskId, duplicateAction] of duplicateActions) {
                taskIdMapDuplicateActions[taskId] = duplicateAction;
            }

            return mutate({
                socket,
                kind: EnqueueKind.IMPORT_CANDIDATE,
                selected: {
                    hashes: [session.folder_hash],
                    paths: [session.folder_path],
                },
                candidate_ids: taskIdMap,
                duplicate_actions: taskIdMapDuplicateActions,
            });
        },
        mutateAsync: async () => {
            const taskIdMap: TaskIdMap<string | CandidateChoiceFallback> = {};
            const taskIdMapDuplicateActions: TaskIdMap<DuplicateAction> = {};

            for (const [taskId, candidateId] of selectedCandidateIds) {
                taskIdMap[taskId] = candidateId;
            }
            for (const [taskId, duplicateAction] of duplicateActions) {
                taskIdMapDuplicateActions[taskId] = duplicateAction;
            }

            return await mutateAsync({
                socket,
                kind: EnqueueKind.IMPORT_CANDIDATE,
                selected: {
                    hashes: [session.folder_hash],
                    paths: [session.folder_path],
                },
                candidate_ids: taskIdMap,
                duplicate_actions: taskIdMapDuplicateActions,
            });
        },
    };
};

/** Add/Search a candidate
 * for a given session.
 *
 * A session can be uniquely identified by
 * its folder_hash.
 *
 * Mostly an overload of the enqueue mutation.
 * FIXME: We might want to remove this
 */
export const addCandidateMutationOptions: UseMutationOptions<
    JobStatusUpdate[],
    APIError,
    {
        socket: StatusSocket | null;
        task_id: string;
    } & Omit<EnqueuePreviewAddCandidate, 'kind'>
> = {
    mutationFn: async ({ socket, task_id, ...extra }) => {
        // Generate a unique job reference for each folder
        // to avoid collisions
        const jobRefs = [`${task_id}-${Date.now()}-${Math.random()}`];

        const promiseResult = waitForJobUpdate({
            socket: socket,
            jobRef: jobRefs,
        });

        const res = await fetch('/session/add_candidates', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                task_id: task_id,
                job_frontend_refs: jobRefs,
                ...extra,
            }),
        });

        // No need to process the direct response, just for debugging.
        // We only enqueue and that usually works. But the job runs in the background
        // and conveys errors via websocket
        const _data = (await res.json()) as JobStatusUpdate;

        // Wait for the job to finish or send other (fail) updates
        const jobUpdates: JobStatusUpdate[] = await promiseResult;
        for (const jobUpdate of jobUpdates) {
            if (jobUpdate.exc !== null && jobUpdate.exc !== undefined) {
                throw new APIError(jobUpdate.exc);
            }
        }
        return jobUpdates;
    },
    onSuccess: async (_data, { ...variables }, onMutateResults, context) => {
        // reuse base onSuccess to invalidate session
        return await enqueueMutationOptions.onSuccess?.(
            _data,
            {
                ...variables,
                kind: EnqueueKind.PREVIEW_ADD_CANDIDATES,
                selected: {
                    // unpack our list of job updates to clear the cashes
                    // for the relevant sessions
                    hashes: [_data[0].job_metas[0].folder_hash],
                    paths: [_data[0].job_metas[0].folder_path],
                },
            },
            onMutateResults,
            context
        );
    },
};

/** Wait for a job update
 *
 * Waits for a status update via the webssocket
 * connection. If no socket is provided, it will
 * resolve to the first job update.
 */
async function waitForJobUpdate({
    socket,
    jobRef,
    timeout = 30_000,
}: {
    socket: StatusSocket | null;
    jobRef: string | string[];
    timeout?: number;
}) {
    if (!socket) {
        return Promise.resolve([] as JobStatusUpdate[]);
    }

    let handleUpdate: (data: JobStatusUpdate) => void;
    const jobRefs = Array.isArray(jobRef) ? jobRef : [jobRef];

    // keep track of matched refs
    const matchedRefs = new Set<string>();
    const matches: JobStatusUpdate[] = [];

    const promiseTimeout = new Promise<never>((_, reject) => {
        setTimeout(() => {
            socket.off('job_status_update', handleUpdate);
            reject(
                new Error(
                    'Timeout: Waiting for a job update took longer than 30 seconds'
                )
            );
        }, timeout);
    });

    const promiseSuccess = new Promise<JobStatusUpdate[]>((resolve) => {
        handleUpdate = (data: JobStatusUpdate) => {
            console.log('Socket Job update', data);
            data.job_metas.forEach((meta) => {
                if (!meta.job_frontend_ref) {
                    return;
                }
                if (jobRefs.includes(meta.job_frontend_ref)) {
                    matchedRefs.add(meta.job_frontend_ref);
                    matches.push(data);

                    // Resolve only when all jobRefs are matched
                    if (matchedRefs.size === jobRefs.length) {
                        socket.off('job_status_update', handleUpdate);
                        resolve(matches);
                    }
                }
            });
        };
        socket.on('job_status_update', handleUpdate);
    });

    return Promise.race([promiseSuccess, promiseTimeout]);
}

/* ----------------------------- Session status ----------------------------- */

/** Canonical per-folder cache entry for a folder's status.
 *
 * Prefer hydrating this via `ensureStatuses` (single batch request);
 * the queryFn here is the fallback for a lone folder. Stays fresh until
 * explicitly updated via the status socket.
 */
export const statusQueryOptions = (folderHash: string, folderPath: string) => ({
    queryKey: ['session', folderHash, 'status'],
    staleTime: Infinity,
    queryFn: async (): Promise<FolderStatusUpdate | null> => {
        const params = new URLSearchParams();
        params.append('folder_hash', folderHash);
        params.append('folder_path', folderPath);
        const response = await fetch(`/session/status?${params.toString()}`);
        const statuses = (await response.json()) as FolderStatusUpdate[];
        return (
            statuses.find((status) => status.hash === folderHash) ??
            statuses.find((status) => status.path === folderPath) ??
            null
        );
    },
});

/**
 * Fetch statuses for many folders in a single request and populate each
 * folder's canonical cache entry. Only folders not cached yet are requested;
 * folders without a status are cached as null so they are not refetched.
 */
export async function ensureStatuses(
    folders: Array<{ hash: string; path: string }>
): Promise<void> {
    const missing = folders.filter(
        (folder) =>
            queryClient.getQueryData<FolderStatusUpdate | null>(
                statusQueryOptions(folder.hash, folder.path).queryKey
            ) === undefined
    );

    if (missing.length === 0) {
        return;
    }

    const params = new URLSearchParams();
    missing.forEach((folder) => {
        params.append('folder_hash', folder.hash);
        params.append('folder_path', folder.path);
    });
    const response = await fetch(`/session/status?${params.toString()}`);
    const statuses = (await response.json()) as FolderStatusUpdate[];
    const byHash = new Map<string, FolderStatusUpdate>();
    const byPath = new Map<string, FolderStatusUpdate>();
    for (const status of statuses) {
        if (!byHash.has(status.hash)) {
            byHash.set(status.hash, status);
        }
        if (!byPath.has(status.path)) {
            byPath.set(status.path, status);
        }
    }

    for (const folder of missing) {
        queryClient.setQueryData<FolderStatusUpdate | null>(
            statusQueryOptions(folder.hash, folder.path).queryKey,
            byHash.get(folder.hash) ?? byPath.get(folder.path) ?? null
        );
    }
}

/* -------------------------- Minimal session info -------------------------- */

/** Per-folder cache entry for the best-match chip info.
 *
 * Fallback for a single folder; use `ensureMinimalSessionData` for batches.
 * Stays fresh until invalidated via `invalidateSession`.
 */
export const minimalSessionQueryOptions = (
    folderHash: string,
    folderPath: string
) => ({
    queryKey: ['session', folderHash, 'minimal'],
    staleTime: Infinity,
    queryFn: async (): Promise<MinimalSession | null> => {
        const params = new URLSearchParams();
        params.append('folder_hash', folderHash);
        params.append('folder_path', folderPath);
        const response = await fetch(`/session/minimal?${params.toString()}`);
        // Returns mapping from given hash to found session
        // Care! : The MinimalSession does not necessarly have the same folder hash
        const res = (await response.json()) as Record<string, MinimalSession>;

        for (const folder_hash_org in res) {
            const session = res[folder_hash_org];

            if (session && session.folder_hash !== folderHash) {
                queryClient.setQueryData<MinimalSession | null>(
                    ['session', session.folder_hash, 'minimal'],
                    session
                );
            }
        }

        return res[folderHash] ?? null;
    },
});

/**
 * Fetch minimal chip info for many folders in one request and populate their
 * canonical cache entries. Skips cached folders; caches null for folders
 * without a session so they are not refetched.
 */
export async function ensureMinimalSessions(
    folders: Array<{ hash: string; path: string }>
): Promise<void> {
    const missing = folders.filter(
        (folder) =>
            queryClient.getQueryData<MinimalSession | null>(
                minimalSessionQueryOptions(folder.hash, folder.path).queryKey
            ) === undefined
    );

    if (missing.length === 0) {
        return;
    }

    const params = new URLSearchParams();
    missing.forEach((folder) => {
        params.append('folder_hash', folder.hash);
        params.append('folder_path', folder.path);
    });
    const response = await fetch(`/session/minimal?${params.toString()}`);
    const res = (await response.json()) as Record<string, MinimalSession>;

    missing.forEach((folder) => {
        queryClient.setQueryData<MinimalSession | null>(
            minimalSessionQueryOptions(folder.hash, folder.path).queryKey,
            res[folder.hash] ?? null
        );
    });
}
