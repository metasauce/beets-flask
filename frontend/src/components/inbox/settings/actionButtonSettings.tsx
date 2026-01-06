import { ChevronDownIcon, PlusIcon, RotateCcwIcon, XIcon } from 'lucide-react';
import { useCallback, useMemo, useRef, useState } from 'react';
import {
    DndContext,
    DragEndEvent,
    DragOverEvent,
    DragOverlay,
    KeyboardSensor,
    PointerSensor,
    UniqueIdentifier,
    useDroppable,
    useSensor,
    useSensors,
} from '@dnd-kit/core';
import {
    arrayMove,
    horizontalListSortingStrategy,
    SortableContext,
    sortableKeyboardCoordinates,
    useSortable,
    verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import {
    Box,
    BoxProps,
    Button,
    ButtonGroup,
    ButtonProps,
    Checkbox,
    DialogActions,
    DialogContent,
    FormControl,
    FormHelperText,
    IconButton,
    InputLabel,
    lighten,
    MenuItem,
    Select,
    SxProps,
    TextField,
    Theme,
    Typography,
    useTheme,
} from '@mui/material';

import {
    Action,
    ACTIONS,
    DEFAULT_INBOX_FOLDER_FRONTEND_CONFIG,
    InboxFolderFrontendConfig,
    useConfig,
} from '@/api/config';
import { Dialog } from '@/components/common/dialogs';

import { ActionIcon } from '../actions/buttons';
import {
    getActionDescription,
    getActionOptionDescription,
} from '../actions/descriptions';

/** A list to add new action and arrange actions.
 *
 */
export function ActionButtonSettings({
    actionButtons,
    setActionButtons,
}: {
    actionButtons: InboxFolderFrontendConfig['actionButtons'];
    setActionButtons: (
        actionButtons: InboxFolderFrontendConfig['actionButtons']
    ) => void;
}) {
    return (
        <Box
            sx={{
                width: '100%',
                display: 'flex',
                flexDirection: 'column',
            }}
        >
            <Typography
                variant="h6"
                sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 1,
                }}
                gutterBottom
            >
                Action Buttons
                <IconButton>
                    <RotateCcwIcon
                        size={16}
                        onClick={() =>
                            setActionButtons(
                                DEFAULT_INBOX_FOLDER_FRONTEND_CONFIG.actionButtons
                            )
                        }
                    />
                </IconButton>
            </Typography>
            <Typography variant="body2" color="text.secondary">
                Arrange the action buttons for your inbox folder. You can drag
                and drop them to reorder or move them between primary,
                secondary, and extra sections.
            </Typography>
            <Wrapper
                actionButtons={actionButtons}
                setActionButtons={setActionButtons}
            />
        </Box>
    );
}

function Wrapper({
    actionButtons,
    setActionButtons,
}: {
    actionButtons: InboxFolderFrontendConfig['actionButtons'];
    setActionButtons: (
        actionButtons: InboxFolderFrontendConfig['actionButtons']
    ) => void;
}) {
    // State to keep track of currently active (being dragged) item
    const [activeAction, setActiveAction] = useState<Action | null>(null);
    // Keep track of items after move to a new container
    const actionsBeforeDrag = useRef<
        null | InboxFolderFrontendConfig['actionButtons']
    >(null);

    // Convert buttons to ids to use in SortableContext
    // containerId to UniqueIdentifier[]
    const items: Record<string, UniqueIdentifier[]> = useMemo(() => {
        const ids: Record<string, UniqueIdentifier[]> = {};
        for (const [containerId, config] of Object.entries(actionButtons)) {
            ids[containerId] = config.actions.map((action) =>
                JSON.stringify(action)
            );
        }
        return ids;
    }, [actionButtons]);

    // Allow use pointers and keyboard sensors for drag and drop
    const sensors = useSensors(
        useSensor(PointerSensor, {
            activationConstraint: {
                distance: 5, // Minimum distance to start dragging
            },
        }),
        useSensor(KeyboardSensor, {
            coordinateGetter: sortableKeyboardCoordinates,
        })
    );

    // Function to find which container an item belongs to
    const findContainer = useCallback(
        (
            id: UniqueIdentifier
        ): 'primary' | 'secondary' | 'extra' | undefined => {
            // if the id is a container id itself
            if (id in items)
                return id as 'primary' | 'secondary' | 'extra' | undefined;

            // find the container by looking into each of them
            return Object.keys(items).find((containerId) =>
                items[containerId].includes(id)
            ) as 'primary' | 'secondary' | 'extra' | undefined;
        },
        [items]
    );

    // Function called when an item is dragged over another container
    // allows to move items between containers (e.g. between primary and secondary)
    const handleDragOver = useCallback(
        ({ active, over }: DragOverEvent) => {
            if (!over || active.id in items) {
                // Early return if no over item or if the active item is a container
                return;
            }

            const { id: activeId } = active;
            const { id: overId } = over;

            const activeContainer = findContainer(activeId);
            const overContainer = findContainer(overId);
            console.log(activeContainer, overContainer);

            if (!overContainer || !activeContainer) {
                // No valid container found, do nothing
                return;
            }
            if (activeContainer == overContainer) {
                return;
            }

            const before = structuredClone(items);
            const activeItems = before[activeContainer];
            const overItems = before[overContainer];
            const activeIndex = activeItems.indexOf(activeId);
            const overIndex = overItems.indexOf(overId);

            const isBelowOverItem =
                over &&
                active.rect.current.translated &&
                active.rect.current.translated.top >
                    over.rect.top + over.rect.height;

            const modifier = isBelowOverItem ? 1 : 0;

            const newIndex =
                overIndex >= 0 ? overIndex + modifier : overItems.length + 1;

            // remove old
            const newConfig = structuredClone(actionButtons);
            newConfig[activeContainer] = {
                ...newConfig[activeContainer],
                actions: newConfig[activeContainer].actions.filter(
                    (_, idx) => idx !== activeIndex
                ),
            };

            newConfig[overContainer].actions.splice(
                newIndex,
                0,
                actionButtons[activeContainer].actions[activeIndex]
            );

            setActionButtons(newConfig);
        },
        [actionButtons, findContainer, items, setActionButtons]
    );

    const handleDragStart = useCallback(
        ({ active }: { active: { id: UniqueIdentifier } }) => {
            // Store the items before the drag starts
            actionsBeforeDrag.current = structuredClone(actionButtons);
            const activeContainer = findContainer(active.id);
            if (!activeContainer) {
                // If the active item is not in any container, do nothing
                setActiveAction(null);
                return;
            }
            const idx = items[activeContainer].indexOf(active.id);
            if (idx === -1) {
                // If the active item is not found in the container, do nothing
                setActiveAction(null);
                return;
            }

            // If the active item is in the primary or secondary container, we can directly access the action
            setActiveAction(actionButtons[activeContainer].actions[idx]);
        },
        [actionButtons, findContainer, items]
    );

    const handleDragCancel = useCallback(() => {
        // Reset items to their state before the drag started
        if (actionsBeforeDrag.current) {
            setActionButtons(actionsBeforeDrag.current);
        }
        setActiveAction(null);
    }, [setActionButtons]);

    const handleDragEnd = useCallback(
        ({ active, over }: DragEndEvent) => {
            const activeContainer = findContainer(active.id);
            if (!over || !activeContainer) {
                setActiveAction(null);
                return;
            }

            const { id: activeId } = active;
            const { id: overId } = over;

            const overContainer = findContainer(overId);

            if (!overContainer) {
                setActiveAction(null);
                return;
            }

            const activeIndex = items[activeContainer].indexOf(activeId);
            const overIndex = items[overContainer].indexOf(overId);

            if (activeIndex !== overIndex) {
                const newConfig = structuredClone(actionButtons);
                newConfig[overContainer].actions = arrayMove(
                    newConfig[overContainer].actions,
                    activeIndex,
                    overIndex
                );

                setActionButtons(newConfig);
            }
            setActiveAction(null);
        },
        [findContainer, items, actionButtons, setActionButtons]
    );

    return (
        <DndContext
            sensors={sensors}
            onDragOver={handleDragOver}
            onDragStart={handleDragStart}
            onDragCancel={handleDragCancel}
            onDragEnd={handleDragEnd}
        >
            <Box
                sx={(theme) => ({
                    display: 'flex',
                    flexDirection: 'row-reverse',
                    gap: 1,
                    width: '100%',
                    marginBottom: 1,
                    marginTop: 1,
                    [theme.breakpoints.down('tablet')]: {
                        flexDirection: 'column',
                    },
                })}
            >
                <DroppableContainer
                    id="primary"
                    sx={{
                        minHeight: '300px',
                        height: '100%',
                        alignItems: 'flex-start',
                        display: 'flex',
                        gap: 0.5,
                    }}
                >
                    <Typography variant="caption" color="text.secondary">
                        Primary actions
                    </Typography>
                    <SortableContext
                        items={items['primary']}
                        strategy={verticalListSortingStrategy}
                    >
                        {actionButtons.primary.actions.map((action, index) => (
                            <SortableAction
                                key={index}
                                id={items['primary'][index]}
                                sx={{
                                    display: 'flex',
                                    justifyContent: 'space-between',
                                    width: '100%',
                                }}
                            >
                                <ActionIcon action={action} />
                                <ActionLabel action={action} />
                                <IconButton
                                    color="default"
                                    size="small"
                                    sx={{ ml: 'auto' }}
                                    onClick={() => {
                                        const newConfig =
                                            structuredClone(actionButtons);
                                        newConfig.primary.actions.splice(
                                            index,
                                            1
                                        );
                                        setActionButtons(newConfig);
                                    }}
                                >
                                    <XIcon size={20} />
                                </IconButton>
                            </SortableAction>
                        ))}
                        {actionButtons.primary.actions.length === 0 && (
                            <Typography
                                variant="body2"
                                color="text.secondary"
                                sx={{
                                    width: '100%',
                                    height: '100%',
                                    textAlign: 'center',
                                    flexGrow: 1,
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    padding: 1,
                                }}
                            >
                                No primary actions configured. Drag and drop
                                actions here or click "Add" to create new
                                actions.
                            </Typography>
                        )}
                        <AddActionButton
                            sx={{ mt: 'auto', ml: 'auto' }}
                            onAdd={(action) => {
                                const newConfig =
                                    structuredClone(actionButtons);
                                newConfig.primary.actions.push(action);
                                setActionButtons(newConfig);
                            }}
                        />
                    </SortableContext>
                </DroppableContainer>
                <DroppableContainer
                    id="secondary"
                    sx={{
                        minHeight: '300px',
                        height: '100%',
                        alignItems: 'flex-start',
                        display: 'flex',
                        gap: 0.5,
                    }}
                >
                    <Typography variant="caption" color="text.secondary">
                        Secondary actions
                    </Typography>
                    <SortableContext
                        items={items['secondary']}
                        strategy={verticalListSortingStrategy}
                    >
                        {actionButtons.secondary.actions.map(
                            (action, index) => (
                                <SortableAction
                                    key={index}
                                    id={items['secondary'][index]}
                                    sx={{
                                        display: 'flex',
                                        justifyContent: 'space-between',
                                        gap: 1,
                                        width: '100%',
                                    }}
                                    variant="outlined"
                                >
                                    <ActionIcon action={action} />
                                    <ActionLabel action={action} />
                                    <IconButton
                                        color="default"
                                        size="small"
                                        sx={{ ml: 'auto' }}
                                        onClick={() => {
                                            const newConfig =
                                                structuredClone(actionButtons);
                                            newConfig.secondary.actions.splice(
                                                index,
                                                1
                                            );
                                            setActionButtons(newConfig);
                                        }}
                                    >
                                        <XIcon size={20} />
                                    </IconButton>
                                </SortableAction>
                            )
                        )}
                        {actionButtons.secondary.actions.length === 0 && (
                            <Typography
                                variant="body2"
                                color="text.secondary"
                                sx={{
                                    width: '100%',
                                    height: '100%',
                                    textAlign: 'center',
                                    flexGrow: 1,
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    padding: 1,
                                }}
                            >
                                No secondary actions configured. Drag and drop
                                actions here or click "Add" to create new
                                actions.
                            </Typography>
                        )}
                        <AddActionButton
                            sx={{ mt: 'auto', ml: 'auto' }}
                            onAdd={(action) => {
                                const newConfig =
                                    structuredClone(actionButtons);
                                newConfig.secondary.actions.push(action);
                                setActionButtons(newConfig);
                            }}
                        />
                    </SortableContext>
                </DroppableContainer>
            </Box>
            <DroppableContainer
                id="extra"
                sx={{
                    height: '100%',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'flex-start',
                    minHeight: '80px',
                    gap: 0.5,
                    flexGrow: 1,
                }}
            >
                <Typography variant="caption" color="text.secondary">
                    Extra actions
                </Typography>
                <SortableContext
                    items={items['extra']}
                    strategy={horizontalListSortingStrategy}
                >
                    <Box
                        sx={{
                            width: '100%',
                            display: 'flex',
                            flexDirection: 'row',
                            gap: 2,
                            height: '100%',
                            flexGrow: 1,
                            flexWrap: 'wrap',
                        }}
                    >
                        {actionButtons.extra.actions.map((action, index) => (
                            <SortableActionExtra
                                key={index}
                                id={items['extra'][index]}
                                variant="text"
                            >
                                <Box
                                    sx={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: 1,
                                    }}
                                >
                                    <ActionIcon action={action} />
                                    <Typography
                                        sx={{ flexGrow: 1, textAlign: 'left' }}
                                        variant="body2"
                                    >
                                        {action.label ||
                                            action.name
                                                .replace(/_/g, ' ')
                                                .replace(/^\w/, (c) =>
                                                    c.toUpperCase()
                                                )}
                                    </Typography>
                                    <IconButton
                                        color="secondary"
                                        size="small"
                                        onClick={() => {
                                            const newConfig =
                                                structuredClone(actionButtons);
                                            newConfig.extra.actions.splice(
                                                index,
                                                1
                                            );
                                            setActionButtons(newConfig);
                                        }}
                                    >
                                        <XIcon size={20} />
                                    </IconButton>
                                </Box>
                            </SortableActionExtra>
                        ))}
                        {actionButtons.extra.actions.length === 0 && (
                            <Typography
                                variant="body2"
                                color="text.secondary"
                                sx={{
                                    width: '100%',
                                    height: '100%',
                                    textAlign: 'center',
                                    flexGrow: 1,
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    padding: 1,
                                }}
                            >
                                No extra actions configured. Drag and drop
                                actions here or click "Add" to create new
                                actions.
                            </Typography>
                        )}
                        <AddActionButton
                            sx={{ ml: 'auto' }}
                            onAdd={(action) => {
                                const newConfig =
                                    structuredClone(actionButtons);
                                newConfig.extra.actions.push(action);
                                setActionButtons(newConfig);
                            }}
                        />
                    </Box>
                </SortableContext>
            </DroppableContainer>
            <DragOverlay>
                {activeAction ? (
                    <SortableAction
                        id={'dragging'}
                        sx={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            width: '100%',
                            backgroundColor: 'transparent !important',
                        }}
                    >
                        <ActionIcon action={activeAction} />
                        <ActionLabel action={activeAction} />
                    </SortableAction>
                ) : null}
            </DragOverlay>
        </DndContext>
    );
}

function DroppableContainer({
    id,
    children,
    sx,
}: Omit<BoxProps, 'id'> & { id: UniqueIdentifier }) {
    const { setNodeRef } = useDroppable({
        id,
    });

    return (
        <Box
            ref={setNodeRef}
            sx={[
                {
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    padding: 1,
                    width: '100%',
                    height: '100%',
                    boxShadow: 4,
                },
                // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
                ...(Array.isArray(sx) ? sx : [sx]),
            ]}
        >
            {children}
        </Box>
    );
}

function ActionLabel({ action }: { action: Action }) {
    return (
        <Typography variant="body1" sx={{ flexGrow: 1, textAlign: 'left' }}>
            {action.label ||
                action.name
                    .replace(/_/g, ' ')
                    .replace(/^\w/, (c) => c.toUpperCase())}
        </Typography>
    );
}

function SortableActionExtra({
    id,
    children,
    sx,
    variant = 'outlined',
    ...props
}: { id: UniqueIdentifier; variant?: 'contained' | 'outlined' | 'text' } & Omit<
    BoxProps,
    'id'
>) {
    const {
        attributes,
        listeners,
        setNodeRef,
        transform,
        transition,
        isDragging,
    } = useSortable({
        id,
    });

    const style = transform
        ? {
              transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`,
              transition,
              opacity: isDragging ? 0.5 : 1,
          }
        : undefined;

    return (
        <Box
            ref={setNodeRef}
            sx={[
                style,
                // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
                ...(Array.isArray(sx) ? sx : [sx]),
            ]}
            {...attributes}
            {...listeners}
            {...props}
        >
            <Button variant={variant} color="secondary">
                {children}
            </Button>
        </Box>
    );
}

function SortableAction({
    id,
    children,
    sx,
    variant = 'contained',
    ...props
}: { id: UniqueIdentifier; variant?: 'contained' | 'outlined' | 'text' } & Omit<
    BoxProps,
    'id'
>) {
    const {
        attributes,
        listeners,
        setNodeRef,
        transform,
        transition,
        isDragging,
        newIndex,
    } = useSortable({
        id,
    });

    const style = transform
        ? {
              transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`,
              transition,
              opacity: isDragging ? 0.5 : 1,
          }
        : undefined;

    let extraSx: SxProps<Theme> = {};
    if (newIndex != 0) {
        extraSx = {
            width: 'calc(100% - 8px)', // Adjust width to fit within the container
            backgroundColor: (theme) =>
                lighten(theme.palette.background.paper, 0.05),
            padding: 1,
            marginLeft: '4px',
            display: 'flex',
            justifyContent: 'space-between',
            gap: 1,
            alignItems: 'center',
        };
    }

    return (
        <Box
            ref={setNodeRef}
            sx={[
                style,
                // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
                ...(Array.isArray(sx) ? sx : [sx]),
            ]}
            {...attributes}
            {...listeners}
            {...props}
        >
            {newIndex == 0 ? (
                <ButtonGroup
                    sx={{ width: '100%' }}
                    color="secondary"
                    variant={variant}
                >
                    <Button sx={{ width: '100%', gap: 1 }}>{children}</Button>
                    <Button size="small">
                        <ChevronDownIcon />
                    </Button>
                </ButtonGroup>
            ) : (
                <Box sx={extraSx}>{children}</Box>
            )}
        </Box>
    );
}

function AddActionButton({
    onAdd,
    ...props
}: {
    onAdd: (action: Action) => void;
} & ButtonProps) {
    const theme = useTheme();
    const config = useConfig();
    const [open, setOpen] = useState(false);

    function isEnabled([actionName, _action]: [string, Action]) {
        switch (actionName) {
            case 'import_terminal':
                return config.gui.terminal.enable;
            default:
                return true;
        }
    }

    const defaultActions: Array<Action> = Object.entries(ACTIONS)
        .filter(isEnabled)
        .map(([_, a]) => a);

    const [action, setAction] = useState<Action>(defaultActions[0]);

    return (
        <>
            <Button
                variant="text"
                size="small"
                color="secondary"
                startIcon={<PlusIcon size={theme.iconSize.sm} />}
                onClick={() => setOpen(true)}
                {...props}
            >
                <Typography variant="body2">Add</Typography>
            </Button>
            <Dialog
                open={open}
                onClose={() => {
                    setOpen(false);
                }}
                title_icon={<PlusIcon size={theme.iconSize.lg} />}
                title="Add Action Button"
                color="secondary"
            >
                <DialogContent>
                    <FormControl sx={{ width: '100%' }} color="secondary">
                        <InputLabel id="action-type-label">Type</InputLabel>
                        <Select
                            label="Type"
                            labelId="action-type-label"
                            value={action.name}
                            onChange={(e) => {
                                const selectedAction = defaultActions.find(
                                    (a) => a.name === e.target.value
                                );
                                if (selectedAction) {
                                    setAction(selectedAction);
                                }
                            }}
                            color="secondary"
                            fullWidth
                        >
                            {defaultActions.map((actionOption) => (
                                <MenuItem
                                    key={actionOption.name}
                                    value={actionOption.name}
                                    color="secondary"
                                >
                                    <Box
                                        sx={{
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: 1,
                                        }}
                                    >
                                        <ActionIcon action={actionOption} />
                                        <Typography>
                                            {actionOption.label ||
                                                actionOption.name
                                                    .replace(/_/g, ' ')
                                                    .replace(/^\w/, (c) =>
                                                        c.toUpperCase()
                                                    )}
                                        </Typography>
                                    </Box>
                                </MenuItem>
                            ))}
                        </Select>
                        <FormHelperText>
                            {getActionDescription(action)}
                        </FormHelperText>
                    </FormControl>
                    <FormControl sx={{ width: '100%' }}>
                        <TextField
                            label="Label"
                            value={action.label || ''}
                            onChange={(e) => {
                                setAction((prev) => ({
                                    ...prev,
                                    label: e.target.value,
                                }));
                            }}
                            color="secondary"
                            fullWidth
                            sx={{ marginTop: 2 }}
                            helperText="How this action will be displayed on the button."
                        />
                    </FormControl>
                    {/* Options (if any) for the selected action */}
                    <FormControl sx={{ width: '100%' }}>
                        {action.options &&
                            Object.keys(action.options).length > 0 && (
                                <Box sx={{ marginTop: 2 }}>
                                    <Typography
                                        variant="body2"
                                        color="text.secondary"
                                    >
                                        Options:
                                    </Typography>
                                    {Object.entries(action.options).map(
                                        ([key, value]) => (
                                            <Box>
                                                <Box
                                                    sx={{
                                                        display: 'flex',
                                                        alignItems: 'center',
                                                        gap: 1,
                                                    }}
                                                    key={key}
                                                >
                                                    <Checkbox
                                                        key={key}
                                                        size="small"
                                                        checked={value}
                                                        onChange={(e) => {
                                                            setAction(
                                                                (prev) =>
                                                                    ({
                                                                        ...prev,
                                                                        options:
                                                                            {
                                                                                ...prev.options,
                                                                                [key]: e
                                                                                    .target
                                                                                    .checked,
                                                                            },
                                                                    }) as Action
                                                            );
                                                        }}
                                                        color="secondary"
                                                    />
                                                    <Typography variant="body2">
                                                        {key
                                                            .replace(/_/g, ' ')
                                                            .replace(
                                                                /^\w/,
                                                                (c) =>
                                                                    c.toUpperCase()
                                                            )}
                                                    </Typography>
                                                </Box>
                                                <FormHelperText>
                                                    {getActionOptionDescription(
                                                        key
                                                    )}
                                                </FormHelperText>
                                            </Box>
                                        )
                                    )}
                                </Box>
                            )}
                    </FormControl>
                </DialogContent>
                <DialogActions>
                    <Button
                        variant="text"
                        color="secondary"
                        sx={{
                            mr: 'auto',
                        }}
                        onClick={() => setOpen(false)}
                    >
                        Cancel
                    </Button>
                    <Button
                        variant="contained"
                        color="secondary"
                        startIcon={<PlusIcon size={theme.iconSize.sm} />}
                        onClick={() => {
                            // Placeholder for adding an action
                            setOpen(false);
                            onAdd(action);
                            setAction(defaultActions[0]); // Reset to default action
                            setOpen(false);
                        }}
                    >
                        Add Action
                    </Button>
                </DialogActions>
            </Dialog>
        </>
    );
}
