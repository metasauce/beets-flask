/** Upload dialog
 *
 * Is triggered when files are dropped, there are multiple scenarios:
 * ...
 */

import { CheckIcon, FileMusicIcon, UploadIcon, XIcon } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef } from 'react';
import {
    alpha,
    Box,
    Button,
    DialogContent,
    IconButton,
    LinearProgress,
    TextField,
    Typography,
    useTheme,
} from '@mui/material';

import { useConfig } from '@/api/config';
import { Dialog } from '@/components/common/dialogs';
import { useDragAndDrop } from '@/components/common/hooks/useDrag';
import {
    CancelButton,
    CancelButtonRef,
} from '@/components/common/inputs/cancle';
import { humanizeBytes } from '@/components/common/units/bytes';
import { humanizeDuration } from '@/components/common/units/time';

import { useFileUploadContext } from './context';

export function UploadDialog() {
    const cancelButtonRef = useRef<CancelButtonRef>(null);
    const { fileList, reset, openDialog, setOpenDialog } =
        useFileUploadContext();

    const resetDialog = useCallback(
        (close: boolean = true) => {
            if (close) setOpenDialog(false);
            reset();
        },
        [reset, setOpenDialog]
    );

    // SM@PS: Try to not use 'useEffect' for derived state. Kinda an antipattern
    // React does a good job at this stuff byitself.
    let title = 'Upload files';
    if (fileList.length > 0) {
        title = `Upload ${fileList.length} file${fileList.length !== 1 ? 's' : ''}`;
    }

    // Open dialog when files are added
    useEffect(() => {
        if (fileList.length > 0) {
            setOpenDialog(true);
        }
    }, [fileList.length, setOpenDialog]);

    return (
        <Dialog
            open={openDialog}
            title={title}
            onClose={(_event, reason) => {
                if (reason !== 'backdropClick') resetDialog();
            }}
            title_icon={null}
        >
            <DialogContent>
                <Box
                    sx={{
                        width: '100%',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 2,
                    }}
                >
                    <FolderSelector />
                    <FileDropZone />
                    <UploadFinished />
                    <SelectedFilesListAndProgress />
                    <ErrorMessage />
                    <Box
                        sx={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'flex-end',
                        }}
                    >
                        <CancelButton
                            ref={cancelButtonRef}
                            onCancel={resetDialog}
                            variant="outlined"
                        />
                        <UploadButton
                            onUpload={() => {
                                // Reset dialog when successfully
                                // uploaded after 3 seconds
                                cancelButtonRef.current?.cancelWithTimer(3000);
                            }}
                        />
                    </Box>
                </Box>
            </DialogContent>
        </Dialog>
    );
}

/** Error and success message component
 *
 * Displays error or success messages based on the upload state.
 */
function ErrorMessage() {
    const { isError, error } = useFileUploadContext();

    if (!isError) return null;

    return (
        <Box>
            <Typography variant="body2" color="error">
                {error?.name || 'Error'}
            </Typography>
            <Typography variant="body2" color="error">
                {error?.message ||
                    'An unknown error occurred during file upload.'}
            </Typography>
        </Box>
    );
}

/** Selected files list component
 *
 * This component displays the list of files selected for upload.
 * It allows users to remove files from the list before uploading.
 */
function SelectedFilesListAndProgress() {
    const { fileList, setFileList } = useFileUploadContext();

    const handleRemoveFile = (index: number) => {
        // Remove file from the selected files
        setFileList((prevFiles) => prevFiles.filter((_, i) => i !== index));
    };

    if (fileList.length === 0) {
        return (
            <Typography variant="body2">
                No files selected for upload.
            </Typography>
        );
    }

    return (
        <>
            <Typography
                variant="caption"
                fontWeight="bold"
                color="text.secondary"
            >
                Files:
            </Typography>
            <Box
                sx={{
                    width: '100%',
                    overflowY: 'auto',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 0.5,
                    pl: 0.5,
                }}
            >
                {fileList.map((file, index) => (
                    <FileProgressBar
                        file={file.name}
                        removeFile={() => handleRemoveFile(index)}
                        key={index}
                    />
                ))}
            </Box>
        </>
    );
}

/** Shows a singular file and allow to remove it
 * Also shows upload progress if available
 */
function FileProgressBar({
    file,
    removeFile,
}: {
    file: string;
    removeFile: () => void;
}) {
    const theme = useTheme();
    const { uploadProgress, isIdle, isPending } = useFileUploadContext();

    const fileProgress = useMemo(() => {
        return uploadProgress.files.find((f) => f.name === file);
    }, [uploadProgress, file]);

    let percent = fileProgress?.total
        ? (fileProgress.loaded / fileProgress.total) * 100
        : 0;

    // Workaround for files with 0 bytes
    if (fileProgress?.total == 0 && fileProgress?.finished) {
        percent = 100;
    }

    return (
        <Box
            sx={{
                position: 'relative',
                width: '100%',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
            }}
        >
            <Box
                sx={{
                    position: 'absolute',
                    width: '100%',
                    height: '100%',
                    top: 0,
                    left: 0,
                    zIndex: 0,
                }}
            >
                <LinearProgress
                    variant="determinate"
                    value={percent}
                    sx={{
                        height: `100%`,
                        borderRadius: 1,
                        backgroundColor: 'rgba(255, 255, 255, 0.05)',

                        '& .MuiLinearProgress-bar': {
                            backgroundColor: 'primary.muted',
                        },
                    }}
                />
            </Box>

            <Typography
                variant="body1"
                sx={{
                    zIndex: 1,
                    paddingLeft: 1,
                    flex: 1,
                    wordBreak: 'break-word',
                }}
            >
                {file}
            </Typography>
            <Box sx={{ flexShrink: 0 }}>
                <IconButton
                    size="small"
                    disabled={!isIdle}
                    onClick={removeFile}
                >
                    {fileProgress && isPending && (
                        <Typography variant="body2" fontSize="small">
                            {percent.toFixed(0)}%
                        </Typography>
                    )}
                    {fileProgress?.finished && (
                        <CheckIcon size={theme.iconSize.sm} />
                    )}
                    {isIdle && !fileProgress?.finished && (
                        <XIcon size={theme.iconSize.sm} />
                    )}
                </IconButton>
            </Box>
        </Box>
    );
}

/** Folder selector component
 * This component allows users to specify a subfolder within the selected inbox folder
 * where the files will be uploaded.
 */
function FolderSelector() {
    const { uploadTargetDir, setUploadTargetDir, isIdle } =
        useFileUploadContext();
    const config = useConfig();

    const is_valid = useMemo(() => {
        if (!uploadTargetDir) return true;
        for (const folder of Object.values(config.gui.inbox.folders)) {
            if (uploadTargetDir?.startsWith(folder.path)) return true;
        }
        return false;
    }, [config.gui.inbox.folders, uploadTargetDir]);

    return (
        <TextField
            fullWidth
            error={!is_valid}
            label="Target Folder"
            helperText={is_valid ? null : 'Folder must be inside an inbox'}
            disabled={!isIdle}
            value={uploadTargetDir || ''}
            onChange={(e) => setUploadTargetDir(e.target.value)}
            placeholder="Enter folder name"
            size="small"
            sx={{
                input: {
                    fontFamily: 'monospace',
                    letterSpacing: '0.00938em',
                },
            }}
        />
    );
}

/** Upload button component
 * This component displays a button to start the upload process.
 * It shows the number of selected files and the target upload path.
 */
function UploadButton({ onUpload }: { onUpload: () => void }) {
    const { uploadFiles, isError, isSuccess, isPending, reset, fileList } =
        useFileUploadContext();

    if (isError) return null;

    return (
        <Button
            variant="contained"
            startIcon={<UploadIcon />}
            onClick={() => {
                if (isSuccess) {
                    reset();
                } else {
                    uploadFiles().then(onUpload).catch(console.error);
                }
            }}
            disabled={fileList.length === 0}
            loading={isPending}
        >
            {isSuccess ? 'Upload more files' : 'Upload'}
        </Button>
    );
}

/* -------------------------------- Dropzone -------------------------------- */

function FileDropZone() {
    const theme = useTheme();
    const { fileList, setFileList, isSuccess, isError } =
        useFileUploadContext();
    const ref = useRef<HTMLDivElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const isDragOver = useDragAndDrop(ref, {
        onDrop: (event) => {
            if (!event.dataTransfer) return;
            setFileList((prevFiles) => {
                if (!event.dataTransfer) return prevFiles;
                return [...prevFiles, ...Array.from(event.dataTransfer.files)];
            });
        },
    });

    // Don't show dropzone when we are done,
    // space is taken by upload finished component
    if (isSuccess || isError) return null;

    return (
        <Box
            ref={ref}
            sx={(theme) => ({
                border: '2px dashed',
                paddingInline: 4,
                paddingBlock: 2,
                textAlign: 'center',
                borderRadius: 1,
                gap: 2,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                // On drag over animate the border and slight lift the box
                borderColor: isDragOver
                    ? theme.palette.primary.contrastText
                    : theme.palette.primary.muted,
                boxShadow: isDragOver
                    ? `0px 4px 10px ${theme.palette.primary.main}33`
                    : 'none',
                backgroundColor: isDragOver
                    ? theme.palette.primary.muted
                    : theme.palette.background.paper,
                transition:
                    'border-color 0.2s, box-shadow 0.2s, background-color 0.2s',

                '&:hover': {
                    cursor: 'pointer',
                    backgroundColor: alpha(theme.palette.primary.main, 0.05),
                },
            })}
            onClick={() => fileInputRef.current?.click()}
        >
            <input
                ref={fileInputRef}
                type="file"
                hidden
                multiple
                onChange={(e) => {
                    // Add files to the context
                    const files = Array.from(e.target.files || []);
                    if (files.length > 0) {
                        setFileList((prevFiles) => [...prevFiles, ...files]);
                    }
                }}
            />

            {fileList.length == 0 && (
                // big box when no files added yet.
                <>
                    <Box>
                        <Typography
                            variant="h6"
                            color={
                                isDragOver
                                    ? theme.palette.primary.contrastText
                                    : theme.palette.primary.muted
                            }
                            textAlign="center"
                        >
                            Drag and drop files here
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                            or click to select files
                        </Typography>
                    </Box>

                    <FileMusicIcon
                        size={60}
                        strokeWidth={1}
                        color={
                            isDragOver
                                ? theme.palette.primary.contrastText
                                : theme.palette.primary.muted
                        }
                    />

                    <Typography variant="body2" color="text.secondary">
                        Allowed file types: any
                    </Typography>
                </>
            )}

            {fileList.length > 0 && (
                // otherwise smaller box
                <>
                    <Typography variant="body2" color="text.secondary">
                        Add more files ...
                    </Typography>
                </>
            )}
        </Box>
    );
}

/* ----------------------------- Upload Progress ---------------------------- */

function UploadFinished() {
    const { isPending, isIdle, uploadProgress } = useFileUploadContext();

    if (
        !uploadProgress ||
        !uploadProgress.started ||
        !uploadProgress.finished ||
        isPending ||
        isIdle
    ) {
        return null;
    }

    return (
        <Box
            sx={(theme) => ({
                border: '2px solid',
                borderColor: theme.palette.primary.main,
                color: theme.palette.primary.main,
                paddingInline: 4,
                paddingBlock: 2,
                textAlign: 'center',
                borderRadius: 1,
                gap: 2,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
            })}
        >
            <Typography variant="body2">
                Uploaded {uploadProgress.files.length} file
                {uploadProgress.files.length > 1 ? 's' : ''} (
                {humanizeBytes(uploadProgress.total)}) in{' '}
                {humanizeDuration(
                    (uploadProgress.finished - uploadProgress.started) / 1000
                )}
            </Typography>
        </Box>
    );
}
