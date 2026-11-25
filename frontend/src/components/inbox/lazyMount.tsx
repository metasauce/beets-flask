import { ReactNode, useEffect, useRef, useState } from 'react';
import { Box } from '@mui/material';

/* ----------------------------- Shared observers ----------------------------- */
// One IntersectionObserver per scroll container instead of one per row: an
// inbox can hold thousands of rows.

/** How far outside the visible area rows are kept mounted. */
const ROOT_MARGIN = '1000px 0px';

type VisibilityCallback = (isIntersecting: boolean) => void;

const callbacks = new WeakMap<Element, VisibilityCallback>();
const observers = new WeakMap<Element | Document, IntersectionObserver>();

/** Nearest ancestor that scrolls vertically, or null for the viewport.
 *
 * `rootMargin` only extends the observer root. If the list scrolls inside a
 * container, that container has to be the root, otherwise rows would only be
 * mounted once they are already visible.
 */
function getScrollParent(element: Element): Element | null {
    let parent = element.parentElement;
    while (parent && parent !== document.documentElement) {
        const { overflowY } = getComputedStyle(parent);
        if (overflowY === 'auto' || overflowY === 'scroll') {
            return parent;
        }
        parent = parent.parentElement;
    }
    return null;
}

function getObserver(root: Element | null): IntersectionObserver {
    const key = root ?? document;
    let observer = observers.get(key);
    if (!observer) {
        observer = new IntersectionObserver(
            (entries) => {
                for (const entry of entries) {
                    callbacks.get(entry.target)?.(entry.isIntersecting);
                }
            },
            { root, rootMargin: ROOT_MARGIN }
        );
        observers.set(key, observer);
    }
    return observer;
}

/* --------------------------------- Component -------------------------------- */

/** Mounts its children only while the row is near the viewport.
 *
 * Rendering every folder of a large inbox (thousands of rows, each with
 * chips, buttons and links) makes the page slow to load and to interact with.
 * This keeps a cheap placeholder of the same height in the grid instead and
 * swaps in the real row when it gets close to the viewport.
 *
 * The wrapper is itself a subgrid row, so rows inside it still align with the
 * columns of the surrounding `GridWrapper`.
 */
export function LazyMount({
    children,
    estimatedHeight,
}: {
    children: ReactNode;
    /** Height of the placeholder until the row has been measured once. */
    estimatedHeight: number;
}) {
    const ref = useRef<HTMLDivElement>(null);
    const [isNear, setIsNear] = useState(false);
    // Height the content had when it was last mounted (e.g. an expanded
    // folder), so that the page does not jump when it is unmounted again.
    const [height, setHeight] = useState(estimatedHeight);

    useEffect(() => {
        const element = ref.current;
        if (!element) return;

        callbacks.set(element, (isIntersecting) => {
            if (!isIntersecting) {
                const measured = element.getBoundingClientRect().height;
                if (measured > 0) setHeight(measured);
            }
            setIsNear(isIntersecting);
        });
        const observer = getObserver(getScrollParent(element));
        observer.observe(element);

        return () => {
            observer.unobserve(element);
            callbacks.delete(element);
        };
    }, []);

    return (
        <Box
            ref={ref}
            sx={{
                display: 'grid',
                gridColumn: '1 / -1',
                gridTemplateColumns: 'subgrid',
                gridAutoFlow: 'column dense',
            }}
            style={{ minHeight: isNear ? undefined : height }}
        >
            {isNear ? children : null}
        </Box>
    );
}
