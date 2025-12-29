import { useMutation, UseMutationOptions } from '@tanstack/react-query';
import { useNavigate, UseNavigateResult } from '@tanstack/react-router';

import { APIError } from '@/api/common';
import { Action } from '@/api/config';
import { deleteFoldersMutationOptions } from '@/api/inbox';
import { enqueueMutationOptions } from '@/api/session';
import { StatusSocket } from '@/api/websocket';
import { assertUnreachable } from '@/components/common/debugging/typing';
import { formatDate } from '@/components/common/units/time';
import { useStatusSocket } from '@/components/common/websocket/status';
import {
    TerminalContextI,
    useTerminalContext,
} from '@/components/frontpage/terminal';
import { EnqueueKind } from '@/pythonTypes';

import { InboxCardContext, useInboxCardContext } from '../cards/inboxCard';
import {
    FileUploadContextType,
    useFileUploadContext,
} from '../fileUpload/context';
import {
    FolderSelectionContext,
    useFolderSelectionContext,
} from '../folderSelectionContext';

export function useActionMutation(action: Action) {
    const { socket } = useStatusSocket();
    const selectionContext = useFolderSelectionContext();
    const inboxContext = useInboxCardContext();
    const terminalContext = useTerminalContext();
    const uploadContext = useFileUploadContext();
    const navigate = useNavigate();

    const [options, mutationArgs] = actionMutationOptionsAndArgs(
        action,
        socket,
        selectionContext,
        inboxContext,
        uploadContext,
        terminalContext,
        navigate
    );
    const { mutate, mutateAsync, ...mutations } = useMutation({
        ...options,
    });

    return {
        ...mutations,
        mutate: () => {
            mutate(mutationArgs);
        },
        mutateAsync: () => {
            return mutateAsync(mutationArgs);
        },
    };
}

function actionMutationOptionsAndArgs<T = unknown>(
    action: Action,
    socket: StatusSocket | null,
    selectionContext: FolderSelectionContext,
    inboxContext: InboxCardContext,
    uploadContext: FileUploadContextType,
    terminalContext: TerminalContextI,
    navigate: UseNavigateResult<string>
): [UseMutationOptions<unknown, APIError, T>, T] {
    const { name, options } = action;
    switch (name) {
        case 'retag':
            return [
                enqueueMutationOptions as UseMutationOptions<
                    unknown,
                    APIError,
                    T
                >,
                {
                    socket,
                    kind: EnqueueKind.PREVIEW,
                    group_albums: options?.group_albums ?? false,
                    autotag: options?.autotag ?? true,
                    selected: selectionContext.selected,
                } as T,
            ];
        case 'undo':
            return [
                enqueueMutationOptions as UseMutationOptions<
                    unknown,
                    APIError,
                    T
                >,
                {
                    socket,
                    kind: EnqueueKind.IMPORT_UNDO,
                    delete_files: options?.delete_files ?? true,
                    selected: selectionContext.selected,
                } as T,
            ];
        case 'import_best':
            return [
                enqueueMutationOptions as UseMutationOptions<
                    unknown,
                    APIError,
                    T
                >,
                {
                    socket,
                    kind: EnqueueKind.IMPORT_CANDIDATE,
                    selected: selectionContext.selected,
                } as T,
            ];
        case 'import_bootleg':
            return [
                enqueueMutationOptions as UseMutationOptions<
                    unknown,
                    APIError,
                    T
                >,
                {
                    socket,
                    kind: EnqueueKind.IMPORT_BOOTLEG,
                    selected: selectionContext.selected,
                } as T,
            ];
        case 'delete':
            return [
                deleteFoldersMutationOptions as UseMutationOptions<
                    unknown,
                    APIError,
                    T
                >,
                {
                    // TODO: This is a bit inconsistent, to the other actions
                    folderPaths: selectionContext.selected.paths,
                    folderHashes: selectionContext.selected.hashes,
                } as T,
            ];
        case 'delete_imported_folders':
            return [
                deleteFoldersMutationOptions as UseMutationOptions<
                    unknown,
                    APIError,
                    T
                >,
                {
                    folderPaths: inboxContext.importedFolders.map(
                        (f) => f.full_path
                    ),
                    folderHashes: inboxContext.importedFolders.map(
                        (f) => f.hash
                    ),
                } as T,
            ];
        case 'copy_path':
            return [
                copyPathMutationOptions as UseMutationOptions<
                    unknown,
                    APIError,
                    T
                >,
                {
                    selected: selectionContext.selected,
                    escape: options?.escape ?? true, // default to escaping paths
                } as T,
            ];
        case 'upload':
            return [
                uploadDialogMutationOptions as UseMutationOptions<
                    unknown,
                    APIError,
                    T
                >,
                { ...uploadContext, inboxFolder: inboxContext.folder } as T,
            ];
        case 'import_terminal':
            return [
                importTerminalMutationOptions as UseMutationOptions<
                    unknown,
                    APIError,
                    T
                >,
                {
                    selected: selectionContext.selected,
                    terminalContext,
                    navigate,
                } as T,
            ];
        default:
            return assertUnreachable(name);
    }
}

const copyPathMutationOptions: UseMutationOptions<
    unknown,
    APIError,
    { selected: FolderSelectionContext['selected']; escape: boolean }
> = {
    mutationFn: async ({ selected, escape }) => {
        if (selected.paths.length === 0) {
            throw new Error('No folders selected');
        }

        // If clipboard API is not supported, throw an error
        if (!navigator.clipboard) {
            throw new Error('Clipboard API not supported');
        }

        let selectedPaths: string[];
        let text: string;
        if (escape) {
            selectedPaths = selected.paths.map(_escapePathForBash);
        } else {
            selectedPaths = selected.paths;
        }
        if (selectedPaths.length > 1) {
            text = selectedPaths.join('\\n');
        } else {
            text = selectedPaths.join(' ');
        }

        await navigator.clipboard.writeText(text);
    },
    onSuccess: () => {
        // Optionally, you can show a success message or perform other actions
        console.log('Paths copied to clipboard successfully.');
    },
};

const uploadDialogMutationOptions: UseMutationOptions<
    unknown,
    APIError,
    FileUploadContextType & { inboxFolder: InboxCardContext['folder'] }
> = {
    // eslint-disable-next-line @typescript-eslint/require-await
    mutationFn: async ({ setUploadTargetDir, setOpenDialog, inboxFolder }) => {
        // keep the suggested name consistent with the one used in dropzone
        setUploadTargetDir(
            inboxFolder.full_path +
                `/upload_${formatDate(new Date(), '%Y%m%d_%H%M%S')}`
        );
        setOpenDialog(true);
    },
};

function _escapePathForBash(path: string) {
    // escaping path is fishy, but this seems to be the best compromise
    // https://stackoverflow.com/questions/1779858/how-do-i-escape-a-string-for-a-shell-command-in-node
    return `'${path.replace(/'/g, `'\\''`)}'`;
}

const importTerminalMutationOptions: UseMutationOptions<
    unknown,
    APIError,
    {
        selected: FolderSelectionContext['selected'];
        terminalContext: TerminalContextI;
        navigate: UseNavigateResult<string>;
    }
> = {
    mutationFn: async ({ selected, terminalContext, navigate }) => {
        if (selected.paths.length === 0) {
            throw new Error('No folders selected');
        }

        terminalContext.clearInput();
        let text = '';
        const importId = 'cli-' + Math.random().toString(36).slice(2, 16);
        const importDate = formatDate(new Date(), '%Y%m%d_%H%M%S');
        const selectedPaths = selected.paths.map(_escapePathForBash);

        text = '\\\n  ' + selectedPaths.join(' \\\n  ');
        text += ` \\\n  --set gui_import_id='${importId}'`;
        text += ` \\\n  --set gui_import_date='${importDate}'`;

        terminalContext.inputText(`beet import -t ${text}`);
        await navigate({
            to: '/terminal',
        });
    },
    onSuccess: () => {
        // Optionally, you can show a success message or perform other actions
        console.log('Import command sent to terminal successfully.');
    },
};
