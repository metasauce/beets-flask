import {
    ClipboardIcon,
    EyeIcon,
    EyeOffIcon,
    GroupIcon,
    HistoryIcon,
    ImportIcon,
    RefreshCwIcon,
    TagIcon,
    TerminalIcon,
    Trash2Icon,
    UngroupIcon,
    UploadIcon,
} from 'lucide-react';
import { useState } from 'react';
import {
    Box,
    BoxProps,
    Button,
    ButtonProps,
    Checkbox,
    IconButton,
    Tooltip,
    useTheme,
} from '@mui/material';
import { useMutation } from '@tanstack/react-query';

import {
    Action,
    ActionButtonConfig,
    InboxFolderFrontendConfig,
} from '@/api/config';
import { enqueueMutationOptions } from '@/api/session';
import { assertUnreachable } from '@/components/common/debugging/typing';
import { BootlegIcon } from '@/components/common/icons';
import {
    SplitButtonOptionProps,
    SplitButtonOptions,
} from '@/components/common/inputs/splitButton';
import { useStatusSocket } from '@/components/common/websocket/status';
import { EnqueueKind, JobStatusUpdate } from '@/pythonTypes';

import { ActionDialog } from './dialogs';
import { useActionMutation } from './mutations';

/* ----------------------------- Generic buttons ---------------------------- */

/**
 * Create the actions component from the InboxFolderFrontendConfig
 */
export function InboxActions({
    actionButtons,
}: {
    actionButtons: InboxFolderFrontendConfig['actionButtons'];
}) {
    const hasPrimaryOrSecondaryActions =
        actionButtons.primary.actions.length > 0 ||
        actionButtons.secondary.actions.length > 0;
    const hasExtraActions = actionButtons.extra.actions.length > 0;

    return (
        <>
            <Box
                sx={{
                    display: hasPrimaryOrSecondaryActions ? 'flex' : 'none',
                    gap: 1,
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    flexDirection: 'row-reverse',
                    width: '100%',
                }}
            >
                <ActionButton
                    variant={actionButtons.primary.variant}
                    actions={actionButtons.primary.actions}
                />
                <ActionButton
                    variant={actionButtons.secondary.variant}
                    actions={actionButtons.secondary.actions}
                />
            </Box>
            <Box
                sx={{
                    width: '100%',
                    marginTop:
                        hasPrimaryOrSecondaryActions && hasExtraActions ? 1 : 0,
                    marginLeft: '0 !important',
                    display: 'flex',
                    gap: 2,
                }}
            >
                {actionButtons.extra.actions.map((action, index) => (
                    <ActionButton
                        key={index}
                        variant={actionButtons.extra.variant}
                        actions={[action]} // Wrap in an array to match the expected type
                    />
                ))}
            </Box>
        </>
    );
}

function ActionButton({ variant, actions }: ActionButtonConfig) {
    // This is a placeholder for the actual button implementation

    if (!actions || actions.length === 0) {
        return null; // No actions to display
    }

    if (actions.length === 1) {
        // If there's only one action, we can render it directly
        return <ActionButtonSingle action={actions[0]} variant={variant} />;
    }

    if (actions.length > 1) {
        return <ActionButtonMultiple variant={variant} actions={actions} />;
    }
}

function ActionButtonSingle({
    action,
    onMutate,
    ...props
}: Omit<ButtonProps, 'action'> & {
    action: Action;
    onMutate?: (ret: unknown) => void;
}) {
    const [open, setOpen] = useState(false);
    const { mutateAsync, isPending } = useActionMutation(action);

    // Some actions might have a confirmation dialog, so we need to handle that
    // note: we need to call this without jsx to check if it returns a dialog or not
    const Dialog = ActionDialog({ action, open, setOpen });

    const handleClick = async (
        e: React.MouseEvent<HTMLButtonElement, MouseEvent>
    ) => {
        if (Dialog !== null && !e.shiftKey) {
            e.preventDefault();
            setOpen(true);
            return;
        }
        // If no dialog or shift key is pressed, execute the action immediately
        const r = await mutateAsync();
        onMutate?.(r);
    };

    return (
        <>
            <Button
                onClick={handleClick}
                startIcon={<ActionIcon action={action} />}
                loading={isPending}
                color="secondary"
                {...props}
            >
                {action.label || action.name.replace(/_/g, ' ')}
            </Button>
            {Dialog}
        </>
    );
}

function ActionButtonMultiple({
    actions,
    ...props
}: {
    actions: Action[];
} & Omit<SplitButtonOptionProps, 'options'>) {
    const [open, setOpen] = useState(false);
    const [selectedActionIdx, setSelectedActionIdx] = useState(0);
    const selectedAction = actions[selectedActionIdx];

    const { mutate, isPending } = useActionMutation(selectedAction);

    // Some actions might have a confirmation dialog, so we need to handle that
    // note: we need to call this without jsx to check if it returns a dialog or not
    const Dialog = ActionDialog({ action: selectedAction, open, setOpen });
    const handleClick = (
        e: React.MouseEvent<HTMLButtonElement, MouseEvent>
    ) => {
        if (Dialog !== null && !e.shiftKey) {
            e.preventDefault();
            setOpen(true);
            return;
        }
        // If no dialog or shift key is pressed, execute the action immediately
        mutate();
    };

    // map actions to options for the split button
    const options = actions.map((action) => ({
        label:
            action.label ||
            action.name
                .replace(/_/g, ' ')
                .replace(/\b\w/g, (c) => c.toUpperCase()),
        key: action.name,
        buttonProps: {
            startIcon: <ActionIcon action={action} />,
            //disabled: selected.hashes.length === 0,
        },
    }));

    return (
        <SplitButtonOptions
            color="secondary"
            options={options}
            onClick={(option, event) => {
                handleClick(event);
            }}
            onMenuItemClick={(option, index) => {
                setSelectedActionIdx(index);
            }}
            loading={isPending}
            {...props}
        />
    );
}

// TODO move into icons
export function ActionIcon({ action }: { action: Action | Action['name'] }) {
    const theme = useTheme();

    const size = theme.iconSize.md; // Adjust size as needed

    const name = typeof action === 'string' ? action : action.name;

    switch (name) {
        case 'retag':
            return <TagIcon size={size} />;
        case 'undo':
            return <HistoryIcon size={size} />;
        case 'upload':
            return <UploadIcon size={size} />;
        case 'import_bootleg':
            return <BootlegIcon size={size} />;
        case 'import_best':
            return <ImportIcon size={size} />;
        case 'delete':
            return <Trash2Icon size={size} />;
        case 'delete_imported_folders':
            return <Trash2Icon size={size} />;
        case 'copy_path':
            return <ClipboardIcon size={size} />;
        case 'import_terminal':
            return <TerminalIcon size={size} />;
        default:
            return assertUnreachable(name);
    }
}

/* ---------------------------- Specific Buttons ---------------------------- */

export function RefreshAllFoldersButton() {
    // See inbox2 route
    const { mutate, isPending } = useMutation({
        mutationKey: ['refreshInboxTree'],
    });
    const theme = useTheme();

    return (
        <Tooltip title="Refresh folders">
            <IconButton
                onClick={() => mutate()}
                sx={{
                    animation: isPending ? 'spin 1s linear infinite' : 'none',
                    '@keyframes spin': {
                        from: { transform: 'rotate(0deg)' },
                        to: { transform: 'rotate(360deg)' },
                    },
                }}
                disabled={isPending}
            >
                <RefreshCwIcon size={theme.iconSize.lg} />
            </IconButton>
        </Tooltip>
    );
}

export function RetagButtonGroup({
    selected,
    onRetag,
    sx,
    ...props
}: {
    selected: {
        paths: string[];
        hashes: string[];
    };
    onRetag?: (ret: JobStatusUpdate[]) => void;
} & BoxProps) {
    const theme = useTheme();

    const { socket } = useStatusSocket();
    // TODO: Error handling
    const { mutateAsync, isPending } = useMutation(enqueueMutationOptions);

    const [options, setOptions] = useState<{
        group_albums: boolean;
        autotag: boolean;
    }>({
        group_albums: false,
        autotag: true,
    });

    return (
        <Box
            sx={[
                {
                    display: 'flex',
                    gap: 1,
                    alignItems: 'center',
                },
                // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
                ...(Array.isArray(sx) ? sx : [sx]),
            ]}
            {...props}
        >
            <Tooltip title="Group albums">
                <Checkbox
                    color="secondary"
                    icon={<GroupIcon size={theme.iconSize.lg} />}
                    checkedIcon={<UngroupIcon size={theme.iconSize.lg} />}
                    sx={{
                        margin: '0px',
                        borderRadius: '0px',
                        width: '30px',
                        height: '30px',
                        minHeight: '30px',
                        minWidth: '30px',
                        padding: 0.5,
                    }}
                    checked={!options.group_albums}
                    onChange={(e) => {
                        setOptions((prev) => ({
                            ...prev,
                            group_albums: !e.target.checked,
                        }));
                    }}
                />
            </Tooltip>
            <Tooltip title="Online lookup (autotag)">
                <Checkbox
                    color="secondary"
                    icon={<EyeOffIcon size={theme.iconSize.md} />}
                    checkedIcon={<EyeIcon size={theme.iconSize.md} />}
                    sx={{
                        margin: '0px',
                        borderRadius: '0px',
                        width: '30px',
                        height: '30px',
                        minHeight: '30px',
                        minWidth: '30px',
                        padding: 0.5,
                    }}
                    checked={options.autotag}
                    onChange={(e) => {
                        setOptions((prev) => ({
                            ...prev,
                            autotag: e.target.checked,
                        }));
                    }}
                />
            </Tooltip>
            <Tooltip
                title={`(Re)tag the folder (${options.autotag ? 'with lookup' : 'skipping lookup'}, ${options.group_albums ? 'group by metadata' : 'group by folder'})`}
            >
                <Button
                    variant="contained"
                    color="secondary"
                    onClick={async () => {
                        if (!socket) {
                            console.error('No socket connection');
                            return;
                        }
                        const r = await mutateAsync({
                            socket,
                            selected,
                            kind: EnqueueKind.PREVIEW,
                            ...options,
                        });
                        onRetag?.(r);
                    }}
                    loading={isPending}
                    startIcon={<TagIcon size={theme.iconSize.sm} />}
                >
                    (Re)tag
                </Button>
            </Tooltip>
        </Box>
    );
}
