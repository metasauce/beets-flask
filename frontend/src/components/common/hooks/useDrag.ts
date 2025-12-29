import { useEffect, useState } from 'react';

type Entries<T> = {
    [K in keyof T]: [K, T[K]];
}[keyof T][];

/** Custom hook to manage drag and drop interactions.
 *
 *  If elementRef is null, the hook is attached to the window
 *
 */
export function useDragAndDrop(
    elementRef: React.RefObject<HTMLDivElement | null> | null,
    options?: {
        onDrop?: (event: DragEvent) => void;
        onDragOver?: (event: DragEvent) => void;
        onDragEnter?: (event: DragEvent) => void;
        onDragLeave?: (event: DragEvent) => void;
        onDragStart?: (event: DragEvent) => void;
        onDragEnd?: (event: DragEvent) => void;
        onDropWindow?: (event: DragEvent) => void;
        preventDefault?: boolean;
    }
) {
    const [isDragging, setIsDragging] = useState(false);

    useEffect(() => {
        let element: HTMLDivElement = window as unknown as HTMLDivElement; // cursed typing
        if (elementRef) {
            if (!elementRef.current) return;
            element = elementRef.current;
        }

        const abortController = new AbortController();

        // use the timeout to reset drag state so users dont have to reload the page
        // if something goes wrong
        let timeout: NodeJS.Timeout | null = null;
        const eventHandlers = {
            dragend: (e: DragEvent) => {
                setIsDragging(false);
                options?.onDragEnd?.(e);
            },
            dragleave: (e: DragEvent) => {
                setIsDragging(false);
                options?.onDragLeave?.(e);
            },
            dragover: (e: DragEvent) => {
                setIsDragging(true);
                options?.onDragOver?.(e);
                if (timeout) clearTimeout(timeout);
                timeout = setTimeout(() => {
                    setIsDragging(false);
                }, 20000);
            },
            drop: (e: DragEvent) => {
                setIsDragging(false);
                options?.onDrop?.(e);
            },
            dragstart: options?.onDragStart,
        } as const;

        for (const [event, handler] of Object.entries(eventHandlers) as Entries<
            typeof eventHandlers
        >) {
            if (!handler) continue;
            element.addEventListener(
                event,
                (e) => {
                    if (options?.preventDefault) {
                        e.preventDefault();
                        e.stopPropagation();
                    }
                    handler(e);
                },
                {
                    signal: abortController.signal,
                }
            );
        }

        return () => {
            abortController.abort();
        };
    }, [elementRef, options]);

    return isDragging;
}
