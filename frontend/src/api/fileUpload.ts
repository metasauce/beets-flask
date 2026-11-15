import { Dispatch, SetStateAction, useState } from 'react';
import { useMutation, UseMutationOptions } from '@tanstack/react-query';

import { SerializedException } from '@/pythonTypes';

import { APIError } from './common';

export interface FileUploadProgress {
    name: string;
    total: number; // bytes
    loaded: number;
    started?: number;
    finished?: number;
}

export interface BatchFileUploadProgress {
    // overall progress
    files: FileUploadProgress[];
    currentIndex: number;
    started?: number;
    finished?: number;
    total: number; // bytes
    loaded: number;
}

export const fileUploadMutationOptions: UseMutationOptions<
    { status: string },
    APIError,
    {
        files: File[] | FileList;
        targetDir: string;
        setProgress: Dispatch<SetStateAction<BatchFileUploadProgress>>;
    }
> = {
    mutationFn: async ({ files, targetDir, setProgress }) => {
        let uploadedBytesTotal = 0;
        const totalBytes = Array.from(files).reduce(
            (acc, file) => acc + file.size,
            0
        );
        console.log(
            `Uploading ${files.length} files, total size ${totalBytes} bytes`
        );

        // init progress bars for each file
        // Note that you cannot use an object for the batch progress, because
        // we might not iterate its individual file progress objects in order.
        const started = performance.now();
        setProgress({
            files: Array.from(files).map((file) => ({
                name: file.name,
                total: file.size,
                loaded: 0,
            })),
            currentIndex: 0,
            total: totalBytes,
            loaded: 0,
            started: started,
        });

        // We opted to upload files sequentially
        // TODO: what happens if one of the files fails?
        for (let i = 0; i < files.length; i++) {
            const file = files[i];

            let uploadedBytesFile = 0;
            await uploadFile(file, targetDir, (progressUpdate) => {
                uploadedBytesTotal += progressUpdate.loaded - uploadedBytesFile;
                uploadedBytesFile = progressUpdate.loaded;

                setProgress((prev) => {
                    return {
                        ...prev,
                        files: prev.files.map((f, idx) =>
                            idx === i
                                ? {
                                      ...f,
                                      loaded: progressUpdate.loaded,
                                      started: f.started ?? performance.now(),
                                  }
                                : f
                        ),
                        currentIndex: i,
                        loaded: uploadedBytesTotal,
                    };
                });
            });

            setProgress((prev) => {
                return {
                    ...prev,
                    files: prev.files.map((f, idx) =>
                        idx === i
                            ? {
                                  ...f,
                                  loaded: file.size,
                                  started: f.started ?? performance.now(),
                                  finished: performance.now(),
                              }
                            : f
                    ),
                    currentIndex: i + 1,
                    loaded: uploadedBytesTotal,
                };
            });
            console.debug(
                `Uploaded file ${i + 1}/${files.length}: ${file.name}`
            );
        }

        const finished = performance.now();
        setProgress((prev) => {
            return {
                ...prev,
                finished: finished,
                loaded: totalBytes,
                currentIndex: files.length,
            };
        });
        console.log(
            `Uploaded ${files.length} files, total size ${totalBytes} bytes in ${
                (finished - started) / 1000
            } seconds`
        );
        return { status: 'ok' };
    },
};

/** File level upload
 * @param file The file to upload
 * @param targetDir The target directory on the server
 * @param onProgress Optional callback for progress updates
 */
async function uploadFile(
    file: File,
    targetDir: string,
    onProgress?: (progress: { total: number; loaded: number }) => void
): Promise<{ status: string }> {
    // Validate headers (filename and target dir) before uploading
    // Raises if invalid
    await fetch('/file_upload/validate', {
        method: 'POST',
        headers: {
            'X-Filename': encodeURIComponent(file.name),
            'X-File-Target-Dir': targetDir,
        },
    });

    return new Promise<{ status: string }>((resolve, reject) => {
        const req = new XMLHttpRequest();
        req.responseType = 'json';
        req.open('POST', '/api_v1/file_upload', true);
        req.setRequestHeader('X-Filename', encodeURIComponent(file.name));
        req.setRequestHeader(
            'X-File-Target-Dir',
            encodeURIComponent(targetDir)
        );
        // req.setRequestHeader("Content-Length", String(file.size));

        req.upload.onprogress = (event) => {
            if (event.lengthComputable && onProgress) {
                onProgress({ total: event.total, loaded: event.loaded });
            }
        };

        req.onload = () => {
            if (req.status >= 200 && req.status < 300) {
                // onprogress is not called automatically when finally done
                // onProgress?.({ total: file.size, loaded: file.size });
                console.log('File upload resolve');
                resolve({ status: 'ok' });
            } else {
                const json_error = req.response as SerializedException;
                console.error('File upload error:', json_error);
                reject(new APIError(json_error, req.status));
            }
        };

        req.onerror = () => {
            const json_error = req.response as SerializedException;
            console.error('File upload error:', req);
            reject(new APIError(json_error, req.status));
        };
        req.send(file);
    });
}

export function useFileUpload() {
    const { mutate, mutateAsync, reset, ...props } = useMutation(
        fileUploadMutationOptions
    );
    const [uploadProgress, setProgress] = useState<BatchFileUploadProgress>({
        files: [],
        currentIndex: 0,
        total: 0,
        loaded: 0,
    });

    // TODO: Snackbar on success/error

    return {
        uploadProgress,
        mutate: (files: FileList | File[], targetDir: string) => {
            mutate({ files, targetDir, setProgress: setProgress });
        },
        mutateAsync: (files: FileList | File[], targetDir: string) =>
            mutateAsync({ files, targetDir, setProgress: setProgress }),
        reset: () => {
            reset();
            // Fully reset progress and filelist
            setProgress({
                files: [],
                currentIndex: 0,
                total: 0,
                loaded: 0,
            });
        },
        ...props,
    };
}

export type FileUploadState = ReturnType<typeof useFileUpload>;
