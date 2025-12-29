import { useCallback, useEffect, useRef, useState } from 'react';
import React from 'react';
import { Box } from '@mui/material';
import { useMutation } from '@tanstack/react-query';
import { createFileRoute } from '@tanstack/react-router';

import { fileUploadMutationOptions } from '@/api/fileUpload';

export const Route = createFileRoute('/debug/file_drag')({
    component: RouteComponent,
});

function RouteComponent() {
    return (
        <Box sx={{ position: 'relative', width: '100%', height: '100%' }}>
            <DropZone />
        </Box>
    );
}

function DropZone({ children }: { children?: React.ReactNode }) {
    const ref = useRef<HTMLDivElement>(null);
    const [isOverZone, setIsOverZone] = useState(false);
    const [isOverWindow, setIsOverWindow] = useState(false);

    const resetDragState = useCallback(() => {
        setIsOverZone(false);
        setIsOverWindow(false);
    }, []);

    const { mutate } = useMutation(fileUploadMutationOptions);

    useEffect(() => {
        if (!ref.current) return;

        const dropzoneEl = ref.current;
        const abortController = new AbortController();

        const handleDragOver = (event: DragEvent) => {
            setIsOverZone(true);
            event.preventDefault();
            console.log('File(s) in drop zone');
            // Optionally, you can add visual feedback here
        };

        const handleDrop = (event: DragEvent) => {
            event.preventDefault();
            resetDragState();
            const files = event.dataTransfer?.files;
            if (files && files.length > 0) {
                console.log('Dropped files:', files);
                mutate({
                    files: files,
                    targetDir: '/music/upload/',
                    setProgress: () => {},
                }); // Upload all files
            }
        };

        // Dropzone related drag events
        dropzoneEl.addEventListener('dragover', handleDragOver, {
            signal: abortController.signal,
        });
        dropzoneEl.addEventListener('drop', handleDrop, {
            signal: abortController.signal,
        });
        dropzoneEl.addEventListener('dragleave', () => setIsOverZone(false), {
            signal: abortController.signal,
        });

        // Windows level drag events
        window.addEventListener('dragover', () => setIsOverWindow(true), {
            signal: abortController.signal,
        });
        window.addEventListener('dragend', () => resetDragState(), {
            signal: abortController.signal,
        });
        window.addEventListener('dragleave', () => setIsOverWindow(false), {
            signal: abortController.signal,
        });
        window.addEventListener('drop', (e) => e.preventDefault(), {
            signal: abortController.signal,
        });

        return () => {
            // unregister event listeners on cleanup
            abortController.abort();
        };
    }, [ref, setIsOverZone, setIsOverWindow, resetDragState, mutate]);

    return (
        <Box
            ref={ref}
            sx={{
                position: 'absolute',
                top: 0,
                right: 0,
                border: '2px dashed',
                borderColor: isOverZone ? 'red' : 'black',
                backgroundColor: isOverWindow ? 'lightblue' : 'white',
                zIndex: 1,
                padding: '8px',
                width: '300px',
                height: '300px',
            }}
        >
            {children}
        </Box>
    );
}
