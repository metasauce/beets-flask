import { FolderClockIcon, InfoIcon, SettingsIcon, TagIcon } from 'lucide-react';
import { useState } from 'react';
import {
    Box,
    BoxProps,
    DialogContent,
    IconButton,
    Typography,
    useTheme,
} from '@mui/material';
import { useSuspenseQuery } from '@tanstack/react-query';
import { createFileRoute } from '@tanstack/react-router';

import { Action, useConfig } from '@/api/config';
import { inboxQueryOptions } from '@/api/inbox';
import { MatchChip, StyledChip } from '@/components/common/chips';
import { Dialog } from '@/components/common/dialogs';
import {
    FileTypeIcon,
    FolderStatusIcon,
    FolderTypeIcon,
    PenaltyTypeIcon,
} from '@/components/common/icons';
import { PageWrapper } from '@/components/common/page';
import {
    ActionIcon,
    RefreshAllFoldersButton,
} from '@/components/inbox/actions/buttons';
import { getActionDescription } from '@/components/inbox/actions/descriptions';
import { InboxCard } from '@/components/inbox/cards/inboxCard';
import { FileUploadProvider } from '@/components/inbox/fileUpload/context';
import { DropZone } from '@/components/inbox/fileUpload/dropzone';
import { FolderSelectionProvider } from '@/components/inbox/folderSelectionContext';
import { Folder } from '@/pythonTypes';

/* ---------------------------------- Route --------------------------------- */

export const Route = createFileRoute('/inbox/')({
    component: RouteComponent,
    loader: async ({ context }) => {
        return await context.queryClient.ensureQueryData(inboxQueryOptions());
    },
});

function RouteComponent() {
    const { data: inboxes } = useSuspenseQuery(inboxQueryOptions());

    return (
        <PageWrapper
            sx={(theme) => ({
                display: 'flex',
                flexDirection: 'column',
                minHeight: '100%',
                alignItems: 'center',
                paddingTop: theme.spacing(1),
                paddingInline: theme.spacing(0.5),
                [theme.breakpoints.up('laptop')]: {
                    height: 'auto',
                    paddingTop: theme.spacing(2),
                    paddingInline: theme.spacing(1),
                },
            })}
        >
            <PageHeader inboxes={inboxes} />
            <Box
                sx={{
                    width: '100%',
                    display: 'flex',
                    gap: 2,
                    flexDirection: 'column',
                }}
            >
                <FileUploadProvider>
                    {inboxes.map((folder) => (
                        <FolderSelectionProvider key={folder.full_path}>
                            <DropZone inboxDir={folder.full_path}>
                                <InboxCard
                                    key={folder.full_path}
                                    folder={folder}
                                />
                            </DropZone>
                        </FolderSelectionProvider>
                    ))}
                </FileUploadProvider>
            </Box>
        </PageWrapper>
    );
}

/** A simple route header showing
 * a title and some
 * additional information.
 */
function PageHeader({ inboxes, ...props }: { inboxes: Folder[] } & BoxProps) {
    return (
        <Box
            sx={(theme) => ({
                display: 'grid',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: 2,
                width: '100%',
                gridTemplateColumns: '1fr',
                gridTemplateRows: '1fr',
                paddingInline: 2,

                [theme.breakpoints.down('laptop')]: {
                    paddingTop: 1,
                    paddingInline: 1,
                },
            })}
            {...props}
        >
            <Typography
                variant="h4"
                component="div"
                fontWeight="bold"
                sx={{
                    gridColumn: '1',
                    gridRow: '1',
                    textAlign: 'center',
                }}
            >
                Your inbox{inboxes.length > 1 ? 'es' : ''}
            </Typography>
            <Box
                sx={{
                    alignSelf: 'center',
                    display: 'flex',
                    gap: 1,
                    borderRadius: 1,
                    color: 'secondary.muted',
                    gridColumn: '1',
                    gridRow: '1',
                    justifySelf: 'flex-end',
                }}
            >
                <InfoDescription />
            </Box>
            <Box
                sx={{
                    alignSelf: 'center',
                    display: 'flex',
                    gap: 1,
                    borderRadius: 1,
                    color: 'secondary.muted',
                    gridColumn: '1',
                    gridRow: '1',
                    justifySelf: 'flex-start',
                }}
            >
                <RefreshAllFoldersButton />
            </Box>
        </Box>
    );
}

/** Description of the inbox page, shown as modal on click */
function InfoDescription() {
    const theme = useTheme();
    const config = useConfig();

    const [open, setOpen] = useState(false);
    const { data } = useSuspenseQuery(inboxQueryOptions());

    const handleClose = () => {
        setOpen(false);
    };

    return (
        <>
            <IconButton
                sx={{
                    m: 0,
                    p: 0,
                    color: 'inherit',
                }}
                size="small"
                onClick={() => {
                    setOpen(true);
                }}
            >
                <InfoIcon />
            </IconButton>
            <Dialog
                open={open}
                onClose={handleClose}
                title="Information"
                title_icon={<InfoIcon size={theme.iconSize.lg} />}
            >
                <DialogContent
                    sx={{
                        code: {
                            backgroundColor: theme.palette.background.default,
                            paddingInline: 0.5,
                            paddingBlock: 0.25,
                            borderRadius: 1,
                            fontFamily: 'monospace',
                        },
                        '> p': {
                            marginTop: '0 !important',
                        },
                    }}
                >
                    <Box component="p">
                        The <b>Inbox</b> is your temporary holding area for new
                        music files before they're imported into your library.
                        Drop an album folder into{' '}
                        <Box component="code" whiteSpace="nowrap">
                            {data[0].full_path}
                        </Box>
                        to begin with the tagging and importing process.
                    </Box>
                    <Box component="p">
                        By default new inbox items are automatically tagged
                        after a short delay (configurable in the settings yaml).
                        You can also trigger the tagging manually by using the{' '}
                        <TagIcon
                            size={theme.iconSize.sm - 2}
                            strokeWidth={3.5}
                        />{' '}
                        <b
                            style={{
                                whiteSpace: 'nowrap',
                                display: 'inline-flex',
                                gap: 0.5,
                            }}
                        >
                            Retag
                        </b>{' '}
                        action.
                    </Box>
                    {/* Actions */}
                    <Typography sx={{ fontWeight: 'bold', marginBottom: 0.5 }}>
                        Actions
                    </Typography>
                    <Box component="p">
                        You may trigger an action on one or multiple folders by
                        selecting them and then clicking on one of the action
                        buttons that appear at the bottom of the inbox.
                    </Box>
                    <Box component="p">
                        You may configure the available actions and their order
                        for each inbox using the settings button{' '}
                        <SettingsIcon size={theme.iconSize.sm} /> in the top
                        right corner of each inbox card.
                    </Box>
                    <Box
                        sx={{
                            display: 'grid',
                            columnGap: 1,
                            gridTemplateColumns: 'auto auto',
                            gridAutoRows: 'min-content min-content',
                            pl: 1,
                            rowGap: 1,
                        }}
                        component="p"
                    >
                        <ActionInfo action="retag"/>
                        <ActionInfo action="import_best"/>
                        <ActionInfo action="import_bootleg"/>
                        {config.gui.terminal.enable ?? <ActionInfo action="import_terminal"/>}
                        <ActionInfo action="copy_path"/>
                        <ActionInfo action="delete"/>
                        <ActionInfo action="undo"/>
                        <ActionInfo action="upload"/>
                    </Box>
                    {/* Tree view */}
                    <Typography sx={{ fontWeight: 'bold', marginBottom: 0.5 }}>
                        Tree view
                    </Typography>
                    <Box component="p">
                        The tree view shows the folder structure of your inbox.
                        This is very similar to a typical file explorer. You max
                        expand and collapse folders by clicking on the chevron
                        icon.
                    </Box>
                    <Box sx={{ pl: 1 }} component="p">
                        <Box
                            sx={{
                                display: 'flex',
                                gap: 1,
                                alignItems: 'center',
                            }}
                        >
                            <FolderTypeIcon
                                isAlbum={false}
                                isOpen={false}
                                size={theme.iconSize.lg}
                            />
                            <FolderTypeIcon
                                isAlbum={false}
                                isOpen={true}
                                size={theme.iconSize.lg}
                            />
                            <Typography>Folders in your inbox</Typography>
                        </Box>
                        <Box
                            sx={{
                                display: 'flex',
                                gap: 1,
                                alignItems: 'center',
                            }}
                        >
                            <FolderTypeIcon
                                isAlbum={true}
                                isOpen={false}
                                size={theme.iconSize.lg}
                            />
                            <FolderTypeIcon
                                isAlbum={true}
                                isOpen={true}
                                size={theme.iconSize.lg}
                            />
                            <Typography>
                                Music album (identified as such by beets)
                            </Typography>
                        </Box>
                        <Box
                            sx={{
                                display: 'flex',
                                gap: 1,
                                alignItems: 'center',
                            }}
                        >
                            <FolderTypeIcon
                                isAlbum={true}
                                isOpen={false}
                                isArchive={true}
                                size={theme.iconSize.lg}
                            />
                            <FolderTypeIcon
                                isAlbum={true}
                                isOpen={true}
                                isArchive={true}
                                size={theme.iconSize.lg}
                            />
                            <Typography>
                                Archive file (identified as such by beets)
                            </Typography>
                        </Box>
                        <Box
                            sx={{
                                display: 'flex',
                                gap: 1,
                                alignItems: 'center',
                            }}
                        >
                            <FileTypeIcon
                                type={'mp3'}
                                size={theme.iconSize.lg}
                            />
                            <FileTypeIcon
                                type={'txt'}
                                size={theme.iconSize.lg}
                            />
                            <Typography>
                                Any file (icons varies by file extension)
                            </Typography>
                        </Box>
                    </Box>
                    {/* Chips */}
                    <Typography sx={{ fontWeight: 'bold', marginBottom: 0.5 }}>
                        Chips
                    </Typography>
                    <Box component="p">
                        Once a folder is tagged or imported{' '}
                        <StyledChip
                            label="chips"
                            size="small"
                            sx={{
                                width: 'min-content',
                                display: 'inline-flex',
                            }}
                            variant="outlined"
                        />{' '}
                        will be shown in the row of the folder. These chips
                        indicate the status of the folder and gives additional
                        information about the best tag candidate.
                    </Box>
                    <Box
                        component="p"
                        sx={{
                            display: 'grid',
                            columnGap: 1,
                            rowGap: 0.5,
                            gridTemplateColumns: 'min-content auto',
                            alignItems: 'center',
                            pl: 1,
                        }}
                    >
                        <StyledChip
                            icon={
                                <PenaltyTypeIcon
                                    type="duplicate"
                                    size={theme.iconSize.sm}
                                />
                            }
                            label="Duplicate"
                            size="small"
                            color="error"
                            variant="outlined"
                        />
                        <Typography variant="caption">
                            This album is already in your beets library! Click
                            on the chip to jump to the item in your library.
                        </Typography>
                        <StyledChip
                            icon={
                                <FolderStatusIcon
                                    status={1}
                                    size={theme.iconSize.sm}
                                />
                            }
                            label="status"
                            size="small"
                            variant="outlined"
                            color="info"
                        />
                        <Typography variant="caption">
                            The current status of a the most recent action on
                            this folder. This may indicate the live status if an
                            action is currently running.
                        </Typography>
                        <MatchChip source="mb" distance={0.01} />
                        <Typography variant="caption">
                            Shows the quality and metadata source of the best
                            matching tag candidate. For beets veterans, you may
                            think of this as the data source and penalty.
                        </Typography>
                        <StyledChip
                            icon={<FolderClockIcon size={theme.iconSize.sm} />}
                            label="Integrity"
                            size="small"
                            variant="outlined"
                            color="warning"
                        />
                        <Typography variant="caption">
                            The integrity check of the folder failed. This may
                            be due to changes to a folder after it was tagged or
                            imported.
                        </Typography>
                    </Box>
                </DialogContent>
            </Dialog>
        </>
    );
}

function ActionInfo({ action }: { action: Action['name'] }) {
    return (
        <Box>
            <Box
                sx={{
                    display: 'grid',
                    gap: 1,
                    alignItems: 'center',
                    gridTemplateColumns: 'min-content max-content',
                    flexShrink: 0,
                }}
            >
                <ActionIcon action={action} />
                <Typography>
                    {action
                        .replace(/_/g, ' ')
                        .replace(/\b\w/g, (c) => c.toUpperCase())}
                </Typography>
            </Box>
            <Typography variant="caption" component="div">
                {getActionDescription(action)}
            </Typography>
        </Box>
    );
}
