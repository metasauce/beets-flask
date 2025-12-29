import { useRef } from 'react';
import React from 'react';
import { alpha, Box } from '@mui/material';

import { useDragAndDrop } from '@/components/common/hooks/useDrag';
import { formatDate } from '@/components/common/units/time';

import { useFileUploadContext } from './context';

export function DropZone({
    children,
    inboxDir,
}: {
    children?: React.ReactNode;
    inboxDir: string;
}) {
    const ref = useRef<HTMLDivElement>(null);
    const { isOverWindow, setFileList, setUploadTargetDir } =
        useFileUploadContext();
    const isOverDropZone = useDragAndDrop(ref, {
        onDrop: (event) => {
            if (!event.dataTransfer) return;
            setUploadTargetDir(
                inboxDir + `/upload_${formatDate(new Date(), '%Y%m%d_%H%M%S')}`
            );
            setFileList((prevFiles) => {
                if (!event.dataTransfer) return prevFiles;
                return [...prevFiles, ...Array.from(event.dataTransfer.files)];
            });
        },
    });

    return (
        <Box
            ref={ref}
            sx={{
                position: 'relative',
                zIndex: 1,
            }}
        >
            {children}
            {isOverDropZone && (
                <Box
                    // Style for the currently hovered inbox
                    sx={(theme) => ({
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        right: 0,
                        bottom: 0,
                        borderRadius: 2,
                        border: `2px dashed ${theme.palette.secondary.main}`,
                        backgroundColor: alpha(
                            theme.palette.secondary.main,
                            0.1
                        ),
                        backdropFilter: 'blur(1px)',
                        pointerEvents: 'none',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '2rem',
                        fontWeight: 'bold',
                        color: theme.palette.secondary.main,
                        textShadow: `0 0 8px rgba(0,0,0,0.3)`,
                        zIndex: 10,
                    })}
                >
                    Drop to upload
                </Box>
            )}
            {!isOverDropZone && isOverWindow && (
                <Box
                    // Style for non-hovered inboxes when another is being hovered
                    sx={(theme) => ({
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        right: 0,
                        bottom: 0,
                        borderRadius: 2,
                        border: `2px dashed ${theme.palette.primary.main}`,
                        backgroundColor: alpha(
                            theme.palette.primary.main,
                            0.05
                        ),
                        backdropFilter: 'blur(4px)',
                        margin: -0.5,
                        zIndex: 10,
                    })}
                ></Box>
            )}
        </Box>
    );
}
