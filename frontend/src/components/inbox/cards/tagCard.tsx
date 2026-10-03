import {
    ArrowDownIcon,
    ArrowLeftIcon,
    ArrowRightIcon,
    HistoryIcon,
    SearchXIcon,
    TagIcon,
} from 'lucide-react';
import React, { useEffect, useMemo, useState, useTransition } from 'react';
import {
    Alert,
    AlertProps,
    AlertTitle,
    Box,
    Button,
    Card,
    CircularProgress,
    Divider,
    Typography,
    useTheme,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';

import { APIError } from '@/api/common';
import { sessionQueryOptions, useImportMutation } from '@/api/session';
import { PenaltyTypeIcon, SourceTypeIcon } from '@/components/common/icons';
import {
    DuplicateAction,
    DuplicateActions,
    ImportCandidateLabel,
} from '@/components/import/candidates/actions';
import {
    CandidateSelector,
    ImportedCandidate,
} from '@/components/import/candidates/candidateSelector';
import {
    Progress,
    SerializedCandidateState,
    SerializedException,
    SerializedSessionState,
    SerializedTaskState,
} from '@/pythonTypes';

import { CardHeader } from './common';

/** Everything preview/tag related, there are 2 different preview states
 * 1. SelectingCandidate: Session found, candidates fetched, waiting for user to select
 * 2. SelectedCandidate: Session found, candidate chosen by user and imported
 */
export function TagCard({
    folderHash,
    folderPath,
}: {
    folderHash: string;
    folderPath: string;
}) {
    const { data: session } = useQuery(
        sessionQueryOptions({
            folderPath,
            folderHash,
        })
    );

    if (!session) {
        return null;
    }

    if (
        // TODO: move this error handling into the session query?
        session.exc != null &&
        ![
            'DuplicateException',
            'NotImportedException',
            'NoCandidatesFoundException',
        ].includes(session.exc.type)
    ) {
        throw new APIError(session.exc);
    }

    return (
        <Card
            sx={{
                display: 'flex',
                gap: 2,
                flexDirection: 'column',
                padding: 2,
            }}
        >
            {session.status.progress < Progress.IMPORT_COMPLETED ? (
                <UserSelection session={session} />
            ) : (
                <ChosenCandidatesOverview session={session} />
            )}
        </Card>
    );
}

/** Allows to process one or multiple tasks of a session
 * i.e. choose a candidate for each task.
 *
 * More or less a stepper showing one task at a time.
 */
function UserSelection({ session }: { session: SerializedSessionState }) {
    const [currentTaskIdx, setCurrentTaskIdx] = useState<number>(0);
    const currentTask = session.tasks[currentTaskIdx];

    // Transition to the next task, otherwise the UI will freeze
    const [isPending, startTransition] = useTransition();
    const handleTaskChange = (newIdx: number) => {
        startTransition(() => {
            setCurrentTaskIdx(newIdx);
        });
    };

    //id mapping for duplicate actions and select candidates
    //i.e. task[n] corresponds to duplicateActions[n]
    const [duplicateActions, setDuplicateActions] = useState<
        Map<string, DuplicateAction>
    >(new Map());
    const [selectCandidates, setSelectCandidates] = useState<
        Map<string, string>
    >(() => {
        // Initial candidates are always sorted after fetch (see api/session.ts)
        // starting with asis than sorted by distance/penalty
        const m = new Map<string, string>();
        session.tasks.forEach((task) => {
            const candidates = [...task.candidates, task.asis_candidate];
            if (candidates.length >= 1) {
                m.set(task.id, candidates[0].id);
            }
        });
        return m;
    });

    const selectedCandidate = useMemo(() => {
        if (!currentTask) {
            return undefined;
        }
        const candidate = [
            currentTask.asis_candidate,
            ...currentTask.candidates,
        ].find((cand) => cand.id === selectCandidates.get(currentTask.id));
        return candidate;
    }, [currentTask, selectCandidates]);

    // FIXME: Prop drillig sucks here especially, maybe a context would be better
    const mutation = useImportMutation(
        session,
        selectCandidates,
        duplicateActions
    );

    // Sessions can be served with no tasks (e.g. a preview that is still
    // running or found no files). Guard against rendering the stepper, which
    // would crash on `currentTask` being undefined.
    if (!currentTask) {
        return (
            <CardHeader
                icon={<TagIcon />}
                title="No tasks to process"
                subtitle="This session has no tasks. A preview may still be running, or no files were found to import."
            />
        );
    }

    return (
        <Box
            sx={{
                width: '100%',
                display: 'flex',
                flexDirection: 'column',
                gap: 2,
            }}
        >
            <SelectionHeader
                session={session}
                currentTaskIdx={currentTaskIdx}
            />
            <Divider />
            {/* warnings */}
            {session.exc?.type === 'DuplicateException' && (
                <DuplicateWarning exc={session.exc} />
            )}
            {session.exc?.type === 'NotImportedException' && (
                <AutoImportFailedWarning
                    exc={session.exc}
                    source_type={
                        selectedCandidate?.info.data_source || 'unknown'
                    }
                />
            )}
            {session.exc?.type === 'NoCandidatesFoundException' && (
                <NoCandidatesFoundWarning exc={session.exc} />
            )}
            {session.status.progress == Progress.DELETION_COMPLETED && (
                <UndoneWarning />
            )}
            {/*  */}
            <CandidateSelectionArea
                key={currentTask.id}
                isPending={isPending}
                currentTask={currentTask}
                selectedCandidateId={selectedCandidate?.id}
                onCandidateChange={(id) => {
                    setSelectCandidates((prev) => {
                        const newMap = new Map(prev);
                        newMap.set(currentTask.id, id);
                        return newMap;
                    });
                }}
            />
            <SelectionFooter
                session={session}
                isPending={isPending}
                selectedCandidate={selectedCandidate}
                selectedDuplicateAction={
                    duplicateActions.get(currentTask.id) ?? null
                }
                currentTaskIdx={currentTaskIdx}
                onDuplicateActionChange={(action, taskIdx) => {
                    const task = session.tasks[taskIdx];
                    setDuplicateActions((prev) => {
                        const newMap = new Map(prev);
                        if (action === null) {
                            newMap.delete(task.id);
                            return newMap;
                        }
                        newMap.set(task.id, action);
                        return newMap;
                    });
                }}
                onTaskChange={(newIdx) => handleTaskChange(newIdx)}
                importMutation={mutation}
            />
        </Box>
    );
}

/** Allows for a fixed height if a children is loading
 *
 * This can be used to add a transition loading effect without
 * unnecessary layout shifts.
 *
 */
function SizeFixedWithLoading({
    isLoading,
    children,
    color = 'secondary',
    loadingComponent = undefined,
}: {
    isLoading: boolean;
    children: React.ReactNode;
    loadingComponent?: React.ReactNode;
    color?: 'primary' | 'secondary';
}) {
    const ref = React.useRef<HTMLDivElement>(null);
    const [height, setHeight] = useState<number>(0);

    useEffect(() => {
        if (!ref.current) return;

        //Resize observer
        const observer = new ResizeObserver((entries) => {
            for (const entry of entries) {
                setHeight(entry.contentRect.height);
            }
        });
        observer.observe(ref.current);
        return () => {
            observer.disconnect();
        };
    }, []);

    if (isLoading) {
        return (
            <Box
                sx={{
                    display: 'flex',
                    justifyContent: 'center',
                    alignItems: 'center',
                    height: height + 'px',
                }}
            >
                {loadingComponent != null ? (
                    <CircularProgress color={color} />
                ) : null}
            </Box>
        );
    }

    return <Box ref={ref}>{children}</Box>;
}

/** Header section component */
function SelectionHeader({
    session,
    currentTaskIdx,
}: {
    session: SerializedSessionState;
    currentTaskIdx: number;
}) {
    return (
        <CardHeader
            icon={<TagIcon />}
            title={`Select candidate${session.tasks.length > 1 ? 's' : ''}`}
            subtitle="Choose one of the following candidates to import. The selected candidate will be used to update the metadata of the files."
        >
            {session.tasks.length > 1 && (
                <Box sx={{ ml: 'auto', alignSelf: 'flex-start' }}>
                    <Typography
                        variant="caption"
                        component="div"
                        textAlign="right"
                        fontWeight="bold"
                    >
                        Task {currentTaskIdx + 1} of {session.tasks.length}
                    </Typography>
                </Box>
            )}
        </CardHeader>
    );
}

/** Main selection area component */
function CandidateSelectionArea({
    isPending,
    currentTask,
    selectedCandidateId,
    onCandidateChange,
}: {
    isPending: boolean;
    currentTask: SerializedTaskState;
    selectedCandidateId?: SerializedCandidateState['id'];
    onCandidateChange: (id: string) => void;
}) {
    return (
        <SizeFixedWithLoading isLoading={isPending || !selectedCandidateId}>
            <CandidateSelector
                key={currentTask.id}
                task={currentTask}
                selected={selectedCandidateId!}
                onChange={onCandidateChange}
            />
        </SizeFixedWithLoading>
    );
}

/** Footer with action buttons and status */
function SelectionFooter({
    session,
    isPending,
    selectedCandidate,
    selectedDuplicateAction,
    currentTaskIdx,
    onDuplicateActionChange,
    onTaskChange,
    importMutation,
}: {
    session: SerializedSessionState;
    isPending: boolean;
    currentTaskIdx: number;
    selectedCandidate: SerializedCandidateState | undefined;
    selectedDuplicateAction: DuplicateAction | null;
    onDuplicateActionChange: (
        action: DuplicateAction | null,
        taskIdx: number
    ) => void;
    onTaskChange: (newIdx: number) => void;
    importMutation: ReturnType<typeof useImportMutation>;
}) {
    // Check if their are duplicates
    const hasDuplicates =
        selectedCandidate != undefined &&
        selectedCandidate.duplicate_ids.length > 0;

    let errorMsg: string | undefined;
    if (hasDuplicates && !selectedDuplicateAction) {
        errorMsg = `Please choose an action on how to resolve the duplicates from the library.`;
    }

    const importError = importMutation.error;
    if (importError) {
        errorMsg = importError.message;
    }

    return (
        <Box
            sx={{
                width: '100%',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'flex-end',
                gap: 0.5,
            }}
        >
            <SizeFixedWithLoading
                isLoading={isPending}
                color="secondary"
                loadingComponent={null}
            >
                <StatusBar
                    errorMsg={errorMsg}
                    selectedCandidate={selectedCandidate}
                />
            </SizeFixedWithLoading>
            <ActionButtons
                session={session}
                isPending={isPending}
                currentTaskIdx={currentTaskIdx}
                selectedCandidate={selectedCandidate}
                selectedDuplicateAction={selectedDuplicateAction}
                onDuplicateActionChange={onDuplicateActionChange}
                onTaskChange={onTaskChange}
                nextDisabled={hasDuplicates && !selectedDuplicateAction}
                importMutation={importMutation}
            />
        </Box>
    );
}

/** Status display component */
function StatusBar({
    errorMsg,
    selectedCandidate,
}: {
    errorMsg?: string;
    selectedCandidate: SerializedCandidateState | undefined;
}) {
    return (
        <Box
            sx={{
                width: '100%',
                display: 'flex',
                gap: 1,
                justifyContent: 'flex-end',
            }}
        >
            {errorMsg ? (
                <Typography variant="caption" color="error">
                    {errorMsg}
                </Typography>
            ) : (
                <ImportCandidateLabel
                    candidate={selectedCandidate!}
                    sx={{ textAlign: 'right' }}
                />
            )}
        </Box>
    );
}

/** Action buttons component */
function ActionButtons({
    isPending,
    currentTaskIdx,
    session,
    selectedCandidate,
    selectedDuplicateAction,
    onDuplicateActionChange,
    onTaskChange,
    importMutation,
    nextDisabled,
}: {
    isPending: boolean;
    currentTaskIdx: number;
    session: SerializedSessionState;
    selectedCandidate: SerializedCandidateState | undefined;
    selectedDuplicateAction: DuplicateAction | null;
    onDuplicateActionChange: (
        action: DuplicateAction | null,
        taskIdx: number
    ) => void;
    onTaskChange: (newIdx: number) => void;
    nextDisabled?: boolean;
    importMutation: ReturnType<typeof useImportMutation>;
}) {
    const theme = useTheme();

    const isLastTask = currentTaskIdx === session.tasks.length - 1;
    const isFirstTask = currentTaskIdx === 0;

    return (
        <Box
            sx={{
                display: 'flex',
                gap: 2,
                width: '100%',
                justifyContent: 'flex-end',
            }}
        >
            {!isFirstTask && (
                <Button
                    onClick={() => onTaskChange(currentTaskIdx - 1)}
                    loading={isPending}
                    variant="outlined"
                    color="secondary"
                    sx={{ mr: 'auto' }}
                    startIcon={<ArrowLeftIcon size={theme.iconSize.sm} />}
                >
                    Previous
                </Button>
            )}

            {!isPending &&
                selectedCandidate &&
                selectedCandidate?.duplicate_ids.length > 0 && (
                    <DuplicateActions
                        selectedCandidate={selectedCandidate}
                        duplicateAction={selectedDuplicateAction}
                        setDuplicateAction={(action) =>
                            onDuplicateActionChange(action, currentTaskIdx)
                        }
                    />
                )}

            {!isLastTask ? (
                <Button
                    onClick={() => onTaskChange(currentTaskIdx + 1)}
                    loading={isPending}
                    variant="contained"
                    color="secondary"
                    endIcon={<ArrowRightIcon size={theme.iconSize.sm} />}
                    disabled={nextDisabled}
                >
                    Next
                </Button>
            ) : (
                <Button
                    loading={isPending || importMutation.isPending}
                    variant="contained"
                    color="secondary"
                    endIcon={<ArrowDownIcon size={theme.iconSize.sm} />}
                    disabled={nextDisabled}
                    onClick={async () => {
                        await importMutation.mutateAsync();
                    }}
                >
                    Import
                </Button>
            )}
        </Box>
    );
}

/** Shown if a candidate was already chosen
 * as the session is imported.
 *
 */
function ChosenCandidatesOverview({
    session,
}: {
    session: SerializedSessionState;
}) {
    const nItems = session.tasks.reduce(
        (acc, task) => acc + task.items.length,
        0
    );

    return (
        <>
            <CardHeader
                icon={<TagIcon />}
                title={`Selected candidate${session.tasks.length > 1 ? 's' : ''}`}
                subtitle={`The following candidates were selected for import and imported into your library.`}
            >
                <Box sx={{ ml: 'auto', alignSelf: 'flex-start' }}>
                    {session.tasks.length > 1 && (
                        <Typography
                            variant="caption"
                            component="div"
                            textAlign="right"
                        >
                            {session.tasks.length} tasks
                        </Typography>
                    )}
                    <Typography
                        variant="caption"
                        component="div"
                        textAlign="right"
                    >
                        {nItems} item{nItems > 1 ? 's' : ''}
                    </Typography>
                </Box>
            </CardHeader>
            <Divider />
            <Box
                sx={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 1,
                }}
            >
                <Box
                    sx={{
                        '> div:not(:first-of-type)': {
                            marginTop: 2,
                        },
                    }}
                >
                    {session.tasks.map((task, index) => {
                        return <ImportedCandidate task={task} key={index} />;
                    })}
                </Box>
            </Box>
        </>
    );
}

function DuplicateWarning({
    exc,
    ...props
}: {
    exc: SerializedException;
} & AlertProps) {
    return (
        <Alert
            severity="warning"
            icon={<PenaltyTypeIcon type="duplicate" />}
            sx={{
                '.MuiAlert-message': { width: '100%' },
            }}
            {...props}
        >
            <AlertTitle>Duplicate Warning</AlertTitle>
            <Box>
                {exc.message}
                <br />
                Pick another candidate, or choose what to do with duplicates!
            </Box>
        </Alert>
    );
}

function UndoneWarning({ ...props }: AlertProps) {
    return (
        <Alert
            severity="info"
            icon={<HistoryIcon />}
            sx={{
                '.MuiAlert-message': { width: '100%' },
            }}
            {...props}
        >
            <AlertTitle>Session was undone</AlertTitle>
            <Box>
                You had previously imported this session, but undid the import.
                All imported files have been removed from your library.
            </Box>
        </Alert>
    );
}

function AutoImportFailedWarning({
    exc,
    source_type,
    ...props
}: {
    source_type: string;
    exc: SerializedException;
} & AlertProps) {
    return (
        <Alert
            severity="warning"
            icon={<SourceTypeIcon type={source_type} />}
            sx={{
                '.MuiAlert-message': { width: '100%' },
            }}
            {...props}
        >
            <AlertTitle>Auto import failed</AlertTitle>
            <Box>
                {exc.message}
                <br />
                Maybe try searching for a better candidate?
            </Box>
        </Alert>
    );
}

function NoCandidatesFoundWarning({
    exc,
    ...props
}: {
    exc: SerializedException;
} & AlertProps) {
    return (
        <Alert
            severity="warning"
            icon={<SearchXIcon />}
            sx={{
                '.MuiAlert-message': { width: '100%' },
            }}
            {...props}
        >
            <AlertTitle>No Candidates Found</AlertTitle>
            <Box>{exc.message}</Box>
        </Alert>
    );
}
