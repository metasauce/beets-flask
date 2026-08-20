import { createContext, useContext, useMemo } from 'react';
import {
    Box,
    Card,
    CardActions,
    CardContent,
    Tooltip,
    Typography,
} from '@mui/material';
import { useQueries } from '@tanstack/react-query';

import {
    useInboxFolderConfig,
    useInboxFolderFrontendConfig,
} from '@/api/config';
import { walkFolder } from '@/api/inbox';
import { statusQueryOptions } from '@/api/session';
import { InboxTypeIcon } from '@/components/common/icons';
import { CardHeader } from '@/components/frontpage/statsCard';
import {
    ArchiveComponent,
    FileComponent,
    FolderComponent,
    GridWrapper,
    InboxGridHeader,
} from '@/components/inbox/fileTree';
import { Archive, Folder, FolderStatus } from '@/pythonTypes';

import { InboxActions } from '../actions/buttons';

/** Context for easier use of inbox card related variables child
 * components.
 */
export interface InboxCardContext {
    folder: Folder;
    importedFolders: (Folder | Archive)[];

    // Configs
    folderConfig: ReturnType<typeof useInboxFolderConfig>;
    gridTemplateColumns: ReturnType<
        typeof useInboxFolderFrontendConfig
    >['gridTemplateColumns'];
    actionButtons: ReturnType<
        typeof useInboxFolderFrontendConfig
    >['actionButtons'];
}

const InboxCardContext = createContext<InboxCardContext | null>(null);

export const useInboxCardContext = () => {
    const context = useContext(InboxCardContext);
    if (!context) {
        throw new Error(
            'useInboxCardContext must be used within an InboxCardProvider'
        );
    }
    return context;
};

/** Given a folder get all subfolders
 * that have been imported (i.e. have a status of `FolderStatus.IMPORTED`).
 *
 * Each subfolder's status is read from its canonical cache entry
 * (`statusQueryOptions`), which the inbox route loader batch-hydrates via
 * `ensureStatuses` and the status socket keeps up to date.
 */
function useImportedFolders(folder: Folder) {
    const folders = useMemo(
        () =>
            [...walkFolder(folder)].filter(
                (f) => f.type !== 'file' && f.full_path !== folder.full_path
            ),
        [folder]
    );

    const statuses = useQueries({
        queries: folders.map((f) => statusQueryOptions(f.hash, f.full_path)),
    });

    return folders.filter(
        (f, i) => statuses[i].data?.status === FolderStatus.IMPORTED
    );
}

export function InboxCardProvider({
    folder,
    children,
}: {
    folder: Folder;
    children: React.ReactNode;
}) {
    const folderConfig = useInboxFolderConfig(folder.full_path);
    const { gridTemplateColumns, actionButtons } = useInboxFolderFrontendConfig(
        folder.full_path
    );

    const importedFolders = useImportedFolders(folder);

    return (
        <InboxCardContext.Provider
            value={{
                folder,
                importedFolders,
                folderConfig,
                gridTemplateColumns,
                actionButtons,
            }}
        >
            {children}
        </InboxCardContext.Provider>
    );
}

export function InboxCard({ folder }: { folder: Folder }) {
    return (
        <InboxCardProvider folder={folder}>
            <Card
                sx={(theme) => ({
                    width: '100%',
                    padding: 2,
                    // Content (file tree)
                    '.MuiCardContent-root': {
                        margin: 0,
                        marginTop: 1,
                        paddingInline: 1,
                        paddingBlock: 1.5,
                    },

                    // Actions (buttons)
                    '.MuiCardActions-root': {
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 1,
                    },

                    // Remove some padding on very small screens
                    [theme.breakpoints.down('tablet')]: {
                        padding: 1,
                        paddingInline: 0,
                        '.MuiCardContent-root': {
                            paddingInline: 0.5,
                        },
                        '.MuiCardActions-root': {},
                    },
                })}
            >
                <InboxCardHeader />
                <InboxCardContent />
                <InboxCardActions />
            </Card>
        </InboxCardProvider>
    );
}

function InboxCardHeader() {
    const { folder, folderConfig } = useInboxCardContext();

    const threshold = folderConfig.auto_threshold;

    let tooltip: string;
    switch (folderConfig.autotag) {
        case 'auto':
            tooltip =
                'Automatic tagging and import enabled. ' +
                (1 - threshold) * 100 +
                '% threshold.';
            break;
        case 'preview':
            tooltip = 'Automatic tagging enabled, but no import.';
            break;
        case 'bootleg':
            tooltip = 'Import as-is, and split albums by meta-data.';
            break;
        default:
            tooltip = 'No automatic tagging or import enabled.';
            break;
    }

    return (
        <CardHeader
            key={folder.full_path}
            icon={
                <Tooltip title={tooltip}>
                    <InboxTypeIcon
                        size={24}
                        type={folderConfig.autotag || undefined}
                    />
                </Tooltip>
            }
            dividerPos="70%"
            color="secondary.main"
        >
            <Box
                sx={{
                    display: 'flex',
                    alignItems: 'flex-end',
                    width: '100%',
                    justifyContent: 'space-between',
                    position: 'relative',
                    paddingBottom: 2.5,
                    paddingLeft: 1,
                }}
            >
                {/* file path */}
                <Box
                    sx={{
                        display: 'flex',
                        flexWrap: 'wrap',
                        flexDirection: 'row',
                        alignItems: 'flex-end',
                        width: '100%',

                        columnGap: 0.5,
                        rowGap: 0.1,
                    }}
                >
                    {folderConfig.path
                        .split('/')
                        .filter(Boolean)
                        .map((segment, idx, arr) => (
                            <Typography
                                variant="body2"
                                key={idx}
                                component="span"
                                sx={{
                                    display: 'inline-flex',
                                    whiteSpace: 'nowrap',
                                }}
                            >
                                {`/ ${segment}${idx === arr.length - 1 && folderConfig.path.endsWith('/') ? ' /' : ''}`}
                            </Typography>
                        ))}
                </Box>

                {/* inbox name */}
                <Typography
                    variant="body1"
                    sx={{
                        fontWeight: 'bold',
                        flexShrink: 0,
                        m: 0,
                        p: 0,
                    }}
                >
                    {folderConfig.name}
                </Typography>
            </Box>
        </CardHeader>
    );
}

function InboxCardContent() {
    const {
        folder: inbox,
        folderConfig,
        gridTemplateColumns,
    } = useInboxCardContext();

    return (
        <CardContent>
            <GridWrapper config={gridTemplateColumns}>
                {/* Only show inner folders */}
                <InboxGridHeader inboxFolderConfig={folderConfig} />
                {inbox.children.map((child) => {
                    if (child.type === 'directory') {
                        return (
                            <FolderComponent
                                key={child.hash}
                                folder={child as Folder}
                            />
                        );
                    }
                    if (child.type === 'archive') {
                        return (
                            <ArchiveComponent
                                key={child.hash}
                                archive={child}
                            />
                        );
                    }
                })}

                {/* files at bottom */}
                {inbox.children.map((child) => {
                    if (child.type === 'file') {
                        return (
                            <FileComponent key={child.full_path} file={child} />
                        );
                    }
                })}

                {/* If no inner folders, show a message */}
                {inbox.children.length === 0 && (
                    <Box
                        sx={{
                            gridColumn: '1 / -1',
                            textAlign: 'center',
                            color: 'secondary.muted',
                        }}
                    >
                        No folders in this inbox.
                    </Box>
                )}
            </GridWrapper>
        </CardContent>
    );
}

function InboxCardActions() {
    const { actionButtons } = useInboxCardContext();

    return (
        <CardActions>
            <InboxActions actionButtons={actionButtons} />
        </CardActions>
    );
}
