import { createContext, useContext, useState } from 'react';
import React from 'react';
import { createPortal } from 'react-dom';
import { Box } from '@mui/material';

import { FileUploadState, useFileUpload } from '@/api/fileUpload';
import { useDragAndDrop } from '@/components/common/hooks/useDrag';

import { UploadDialog } from './dialog';

export type FileUploadContextType = Omit<
    FileUploadState,
    'mutate' | 'mutateAsync'
> & {
    fileList: Array<File>;
    setFileList: React.Dispatch<React.SetStateAction<Array<File>>>;
    uploadFiles: () => Promise<{ status: string }>;
    uploadTargetDir: string | null;
    setUploadTargetDir: React.Dispatch<React.SetStateAction<string | null>>;
    openDialog: boolean;
    setOpenDialog: React.Dispatch<React.SetStateAction<boolean>>;
    reset: () => void;

    // drag drop
    isOverWindow: boolean;
};

const FileUploadContext = createContext<FileUploadContextType | null>(null);

// Provider component which allows to
// upload files via drag and drop or file picker
export function FileUploadProvider({
    children,
}: {
    children: React.ReactNode;
}) {
    const [fileList, setFileList] = useState<Array<File>>([]);
    const [uploadTargetDir, setUploadTargetDir] = useState<string | null>(null);
    const [openDialog, setOpenDialog] = useState(false);

    const isOverWindow = useDragAndDrop(null, {
        preventDefault: true,
    });
    const { mutateAsync, reset, ...props } = useFileUpload();

    return (
        <FileUploadContext.Provider
            value={{
                ...props,
                fileList,
                setFileList,
                uploadFiles: async () => {
                    if (!uploadTargetDir) {
                        throw new Error('No target directory set for upload');
                    }
                    return await mutateAsync(fileList, uploadTargetDir);
                },
                reset: () => {
                    reset();
                    setFileList([]);
                    setUploadTargetDir(null);
                },
                uploadTargetDir,
                setUploadTargetDir,
                openDialog,
                setOpenDialog,
                isOverWindow,
            }}
        >
            {children}
            <UploadDialog />
            {createPortal(
                <Box
                    // blur the whole background, including navbars
                    sx={{
                        position: 'fixed',
                        top: 0,
                        left: 0,
                        right: 0,
                        bottom: 0,
                        backgroundColor: 'rgba(0, 0, 0, 0.3)',
                        backdropFilter: 'blur(4px)',
                        pointerEvents: 'none',
                        display: isOverWindow ? 'flex' : 'none',
                    }}
                ></Box>,
                document.body
            )}
        </FileUploadContext.Provider>
    );
}

export function useFileUploadContext() {
    const context = useContext(FileUploadContext);
    if (!context) {
        throw new Error(
            'useFileUploadContext must be used within a FileUploadProvider'
        );
    }
    return context;
}
