import {
    CopyMinusIcon,
    CopyPlusIcon,
    MergeIcon,
    SearchIcon,
    Trash2Icon,
    Wand2,
} from 'lucide-react';
import { useState } from 'react';
import {
    Box,
    Button,
    CircularProgress,
    DialogContent,
    FormHelperText,
    styled,
    TextField,
    ToggleButton,
    ToggleButtonGroup,
    ToggleButtonGroupProps,
    ToggleButtonProps,
    Tooltip,
    Typography,
    TypographyProps,
    useTheme,
} from '@mui/material';
import { useMutation } from '@tanstack/react-query';

import { addCandidateMutationOptions } from '@/api/session';
import { Dialog } from '@/components/common/dialogs';
import { useStatusSocket } from '@/components/common/websocket/status';
import {
    Search,
    SerializedCandidateState,
    SerializedTaskState,
} from '@/pythonTypes';

/** Text that is show as an indicator
 * how good a match is.
 *
 *
 */
function candidateMatchText({
    candidate,
}: {
    candidate: SerializedCandidateState;
}) {
    let text = '';
    const match = 1 - candidate.distance;
    if (match > 0.95) {
        text = 'This is a perfect match!';
    } else if (match > 0.9) {
        text = 'Great choice!';
    } else if (match > 0.8) {
        text = 'Not too shabby, this could work.';
    } else if (match > 0.7) {
        text = "It's fine, I guess...";
    } else if (match > 0.6) {
        text = "Sure, if you're okay with 'average'.";
    } else if (match > 0.5) {
        text = 'I mean, you could do better, but okay.';
    } else if (match > 0.3) {
        text = "Really? This is what you're going with?";
    } else if (match > 0.2) {
        text = "I don't even know why you're considering this.";
    } else if (match > 0.1) {
        text = 'You might want to rethink your choices.';
    } else {
        text = 'This... is a disaster.';
    }

    // Special case for asis
    if (candidate.info.data_source === 'asis') {
        text = 'Fear of the unknown?';
    }

    return text;
}

export function ImportCandidateLabel({
    candidate,
    ...props
}: {
    candidate: SerializedCandidateState;
} & TypographyProps) {
    return (
        <Typography variant="caption" color="textDisabled" {...props}>
            {candidateMatchText({ candidate })}
        </Typography>
    );
}

/* ---------------------------- Duplicate actions --------------------------- */

// override default styling so that the selected button in the buttongroup
// does not look highlighted when the whole group is disabled.
const DuplicateActionButtonGroup = styled(ToggleButtonGroup)(({ theme }) => ({
    '& .MuiToggleButtonGroup-grouped': {
        '&.Mui-selected': {
            backgroundColor: theme.palette.action.selected,
            '&:hover': {
                backgroundColor: theme.palette.action.selected,
            },
        },
        '&.Mui-disabled': {
            '&.Mui-selected': {
                backgroundColor: 'inherit',
                color: theme.palette.text.disabled,
                '&:hover': {
                    backgroundColor: 'inherit',
                },
            },
        },
    },
}));

export type DuplicateAction = 'skip' | 'merge' | 'keep' | 'remove';

/** Actions which are shown if a candidate is already
 * existing in the database. I.e. duplicate
 */
export function DuplicateActions({
    setDuplicateAction,
    duplicateAction,
    selectedCandidate,
    ...props
}: Omit<ToggleButtonGroupProps, 'color'> & {
    duplicateAction: DuplicateAction | null;
    setDuplicateAction: (action: DuplicateAction | null) => void;
    selectedCandidate: SerializedCandidateState;
}) {
    const actions = ['skip', 'merge', 'keep', 'remove'] as const;

    return (
        <DuplicateActionButtonGroup
            exclusive
            color="secondary"
            disabled={selectedCandidate.duplicate_ids.length === 0}
            aria-label="duplicate actions"
            title={
                selectedCandidate.duplicate_ids.length > 0
                    ? 'This candidate is a duplicate of an existing item'
                    : 'No duplicates found'
            }
            {...props}
        >
            {actions.map((action) => (
                <DuplicateActionButton
                    key={action}
                    value={action}
                    selected={duplicateAction === action}
                    onClick={() => {
                        if (action === duplicateAction) {
                            setDuplicateAction(null);
                            return;
                        }
                        setDuplicateAction(action);
                    }}
                    color="secondary"
                />
            ))}
        </DuplicateActionButtonGroup>
    );
}

function DuplicateActionButton({
    value,
    ...props
}: {
    value: DuplicateAction;
} & Omit<ToggleButtonProps, 'value' | 'type'>) {
    const theme = useTheme();

    let Icon = CopyMinusIcon;
    let title = '';
    switch (value) {
        case 'skip':
            Icon = CopyMinusIcon;
            title = "Skip new (don't import)";
            break;
        case 'merge':
            Icon = MergeIcon;
            title = 'Merge new and old into one album';
            break;
        case 'keep':
            Icon = CopyPlusIcon;
            title = 'Keep both, old and new';
            break;
        case 'remove':
            Icon = Trash2Icon;
            title = 'Remove old items';
            break;
        default:
            break;
    }

    return (
        <Tooltip title={title}>
            <ToggleButton
                value={value}
                aria-label={value}
                size="small"
                color="primary"
                {...props}
            >
                <Icon size={theme.iconSize.sm} />
            </ToggleButton>
        </Tooltip>
    );
}

/* -------------------------- Search new candidate -------------------------- */

export function CandidateSearch({ task }: { task: SerializedTaskState }) {
    const theme = useTheme();
    const socket = useStatusSocket().socket;
    const [open, setOpen] = useState(false);
    const [search, setSearch] = useState<Search>({
        search_ids: [],
        search_artist: null,
        search_album: null,
        search_year: null,
    });

    /** Mutation for the search
     * this basically triggers an
     * enqueue of a new task
     */
    const { mutateAsync, isPending, isError, error } = useMutation(
        addCandidateMutationOptions
    );

    return (
        <>
            <Tooltip title="Search for more candidates" placement="top">
                <Button
                    variant="outlined"
                    color="secondary"
                    size="small"
                    onClick={() => setOpen(true)}
                    startIcon={
                        isPending ? (
                            <CircularProgress
                                size={theme.iconSize.sm}
                                color="secondary"
                            />
                        ) : (
                            <SearchIcon size={theme.iconSize.sm} />
                        )
                    }
                >
                    Search
                </Button>
            </Tooltip>
            <Dialog
                title="Search for more candidates"
                open={open}
                onClose={() => setOpen(false)}
                title_icon={<SearchIcon size={theme.iconSize.lg} />}
                disableRestoreFocus={true}
                color="secondary"
            >
                <form
                    onSubmit={async (e) => {
                        e.preventDefault();

                        try {
                            await mutateAsync({
                                socket: socket,
                                task_id: task.id,
                                search: {
                                    [task.id]: search,
                                },
                            });
                            setOpen(false);
                            setSearch({
                                search_ids: [],
                                search_artist: '',
                                search_album: '',
                                search_year: '',
                            });
                        } catch (e) {
                            // dont close the dialog
                            console.error(e);
                        }
                    }}
                >
                    <DialogContent
                        sx={{
                            display: 'flex',
                            flexDirection: 'column',
                            gap: 1.5,
                        }}
                    >
                        <Box
                            sx={{
                                width: '100%',
                                display: 'flex',
                                flexDirection: 'row',
                                gap: 1,
                            }}
                        >
                            <SearchField
                                sx={{ flex: 1 }}
                                id="input-search-id"
                                label="Search by Id"
                                placeholder=""
                                autoFocus
                                helperText="Identifier or URL to search for, can be musicbrainz id, spotify url, etc. depending on your configuration."
                                onChange={(e) => {
                                    setSearch({
                                        ...search,
                                        search_ids: e.target.value
                                            .split(',')
                                            .map((id) => id.trim()),
                                    });
                                }}
                            />
                            <Button
                                variant="outlined"
                                color="secondary"
                                onClick={() => {
                                    const metadata = task.current_metadata;
                                    setSearch({
                                        search_ids: metadata.mb_albumid
                                            ? [metadata.mb_albumid]
                                            : [],
                                        search_artist: metadata.artist,
                                        search_album: metadata.album,
                                        search_year: metadata.year,
                                    });
                                }}
                                startIcon={
                                    <Wand2 size={theme.iconSize.sm} />
                                }
                                sx={{ alignSelf: 'center' }}
                            >
                                Auto-fill
                            </Button>
                        </Box>
                        <Box>
                            <Box
                                sx={{
                                    width: '100%',
                                    display: 'flex',
                                    flexDirection: 'row',
                                    gap: '1rem',
                                }}
                            >
                                <SearchField
                                    sx={{ width: '100%' }}
                                    id="input-search-artist"
                                    label="Search by artist"
                                    placeholder="Artist"
                                    value={search.search_artist || ''}
                                    onChange={(e) => {
                                        setSearch({
                                            ...search,
                                            search_artist: e.target.value,
                                        });
                                    }}
                                />
                                <SearchField
                                    sx={{ width: '100%' }}
                                    id="input-search-album"
                                    label="and album"
                                    placeholder="Album"
                                    value={search.search_album || ''}
                                    onChange={(e) => {
                                        setSearch({
                                            ...search,
                                            search_album: e.target.value,
                                        });
                                    }}
                                />
                                <SearchField
                                    sx={{ width: '100%' }}
                                    id="input-search-year"
                                    label="and year"
                                    placeholder="Year"
                                    value={search.search_year || ''}
                                    onChange={(e) => {
                                        setSearch({
                                            ...search,
                                            search_year: e.target.value,
                                        });
                                    }}
                                />
                            </Box>
                            <FormHelperText
                                sx={(theme) => ({
                                    marginInline: '1rem',
                                    color: theme.palette.text.disabled,
                                    fontSize: theme.typography.caption.fontSize,
                                })}
                            >
                                Search by artist, album and year name to find
                                more candidates. Might take a while.
                            </FormHelperText>
                        </Box>
                        <Box
                            sx={{
                                width: '100%',
                                display: 'flex',
                                justifyContent: 'flex-end',
                                gap: 1,
                                marginTop: 'auto',
                            }}
                        >
                            {isError && (
                                <FormHelperText
                                    error={isError}
                                    sx={{
                                        marginInline: '1rem',
                                        alignSelf: 'flex-end',
                                    }}
                                >
                                    {error.message}
                                </FormHelperText>
                            )}
                            <Button
                                variant="outlined"
                                color="secondary"
                                type="submit"
                                startIcon={
                                    isPending ? (
                                        <CircularProgress
                                            color="secondary"
                                            size={theme.iconSize.sm}
                                        />
                                    ) : (
                                        <SearchIcon size={theme.iconSize.sm} />
                                    )
                                }
                                disabled={isPending}
                            >
                                Search
                            </Button>
                        </Box>
                    </DialogContent>
                </form>
            </Dialog>
        </>
    );
}

const SearchField = styled(TextField)(({ theme }) => ({
    // backgroundColor: theme.palette.background.default,
    borderColor: theme.palette.divider,
    borderRadius: theme.shape.borderRadius,
    '& .MuiOutlinedInput-root': {
        '& fieldset': {
            borderColor: theme.palette.divider,
        },
        '&:hover fieldset': {
            borderColor: theme.palette.secondary.main,
        },
        '&.Mui-focused fieldset': {
            borderColor: theme.palette.secondary.main,
        },
    },
    '& .MuiInputLabel-root': {
        '&.Mui-focused': {
            color: theme.palette.secondary.main,
        },
    },
    '.MuiFormHelperText-root': {
        marginInline: '1rem',
        color: theme.palette.text.disabled,
        fontSize: theme.typography.caption.fontSize,
    },
}));
