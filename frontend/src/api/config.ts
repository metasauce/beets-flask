import { useMemo } from 'react';
import { queryOptions, useSuspenseQuery } from '@tanstack/react-query';

import { useLocalStorage } from '@/components/common/hooks/useLocalStorage';
import { BeetsSchema } from '@/pythonTypes';

import { APIError } from './common';

export interface MinimalConfig extends BeetsSchema {
    // extra fields that are not in the schema:
    beets_metadata_sources: Array<string>;
    beets_version: string;
}

export const configQueryOptions = () =>
    queryOptions({
        queryKey: ['config'],
        queryFn: async () => {
            const response = await fetch(`/config`);
            return (await response.json()) as MinimalConfig;
        },
    });

export const useConfig = () => {
    const { data } = useSuspenseQuery(configQueryOptions());
    return data;
};

/* ---------------------------- Raw config files ---------------------------- */

export const configYamlQueryOptions = (type: 'beets' | 'beetsflask') =>
    queryOptions<{ path: string; content: string }, APIError>({
        queryKey: ['config_yaml', type],
        queryFn: async () => {
            const url =
                type === 'beets' ? `/config/yaml/beets` : `/config/yaml`;
            const response = await fetch(url);
            return (await response.json()) as { path: string; content: string };
        },
    });

// This is kinda intertwined with the fileTree and action buttons as this is
// mainly a frontend configuration. Maybe we should move this to a different file?

export type GridColumn = {
    name: 'selector' | 'tree' | 'chip' | 'actions';
    size: '1fr' | 'auto';
    hidden?: boolean;
};

type ActionOptionMap = {
    retag: {
        group_albums: boolean;
        autotag: boolean;
    };
    undo: {
        delete_files: boolean;
    };
    upload: undefined;
    import_best: undefined;
    import_bootleg: undefined;
    import_terminal: undefined;
    delete: undefined;
    delete_imported_folders: undefined;
    copy_path: {
        escape: boolean; // Whether to escape the path for shell usage
    };
};

export type Action = {
    [K in keyof ActionOptionMap]: {
        name: K;
        label?: string; // Optional label for the action, defaults to name with underscores replaced by spaces
    } & (ActionOptionMap[K] extends undefined
        ? { options?: never }
        : { options: ActionOptionMap[K] });
}[keyof ActionOptionMap];

export type ActionButtonConfig = {
    variant: 'outlined' | 'contained' | 'text';
    // List of actions that this button can perform, e.g. a mapping to our enqueue actions
    actions: Array<Action>;
};

export interface InboxFolderFrontendConfig {
    gridTemplateColumns: Array<GridColumn>;
    actionButtons: {
        primary: ActionButtonConfig;
        secondary: ActionButtonConfig;
        extra: ActionButtonConfig;
    };
}

export const ACTIONS: Record<string, Action> = {
    retag: {
        name: 'retag',
        options: {
            group_albums: false,
            autotag: true,
        },
    },
    undo: {
        name: 'undo',
        options: {
            delete_files: true,
        },
    },
    upload: {
        name: 'upload',
    },
    import_best: {
        name: 'import_best',
    },
    import_bootleg: {
        name: 'import_bootleg',
    },
    import_terminal: {
        name: 'import_terminal',
    },
    delete: {
        name: 'delete',
    },
    delete_imported_folders: {
        name: 'delete_imported_folders',
    },
    copy_path: {
        name: 'copy_path',
        options: {
            escape: true, // Whether to escape the path for shell usage
        },
    },
};

export const DEFAULT_INBOX_FOLDER_FRONTEND_CONFIG: InboxFolderFrontendConfig = {
    gridTemplateColumns: [
        { name: 'selector', size: 'auto' },
        { name: 'tree', size: '1fr' },
        { name: 'chip', size: 'auto' },
        { name: 'actions', size: 'auto' },
    ],
    actionButtons: {
        primary: {
            variant: 'contained',
            actions: [ACTIONS.import_best, ACTIONS.import_bootleg],
        },
        secondary: {
            variant: 'outlined',
            actions: [ACTIONS.retag, ACTIONS.undo, ACTIONS.delete],
        },
        extra: {
            variant: 'text',
            actions: [ACTIONS.delete_imported_folders, ACTIONS.upload],
        },
    },
};

export const useInboxFolderFrontendConfig = (fullpath: string) => {
    const [config, setConfig] = useLocalStorage<InboxFolderFrontendConfig>(
        'inbox_folder_grid_config_' + fullpath,
        DEFAULT_INBOX_FOLDER_FRONTEND_CONFIG
    );

    const setGridTemplateColumns = (columns: Array<GridColumn>) => {
        setConfig({
            ...config,
            gridTemplateColumns: columns,
        });
    };

    const setActionButtons = (actionButtons: {
        primary: ActionButtonConfig;
        secondary: ActionButtonConfig;
        extra: ActionButtonConfig;
    }) => {
        setConfig({
            ...config,
            actionButtons: actionButtons,
        });
    };

    return {
        config,
        gridTemplateColumns: config.gridTemplateColumns,
        actionButtons: config.actionButtons,
        setConfig,
        setGridTemplateColumns,
        setActionButtons,
    };
};

/** Inbox folder config
 *
 * This hook retrieves the configuration for a specific inbox folder,
 * if the folder is not found in the configuration,
 * an error is thrown!
 *
 * Also add the config of the grid to the returned object.
 */
export const useInboxFolderConfig = (full_path: string) => {
    const config = useConfig();

    return useMemo(() => {
        const fc = Object.entries(config.gui.inbox.folders).find(
            ([_k, v]) => v.path === full_path
        );
        if (!fc) {
            throw new Error(
                `No configuration found for inbox folder: ${full_path}`
            );
        }

        return {
            ...fc[1],
            auto_threshold:
                fc[1].auto_threshold ?? config.match.strong_rec_thresh,
        };
    }, [config, full_path]);
};
