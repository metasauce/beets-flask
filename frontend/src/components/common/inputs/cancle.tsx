import { XIcon } from 'lucide-react';
import { useImperativeHandle, useRef, useState } from 'react';
import { Button, ButtonProps } from '@mui/material';

export interface CancelButtonRef {
    cancel: () => void;
    cancelWithTimer: (timeout: number) => void;
}

/** Cancel button
 *
 * Advanced usage:
 *
 * Allows to set a timeout which shown an animation
 * on the button before calling the onCancel function.
 * This can be triggered using the CancelButtonRef. This
 * does not trigger on the button click, only when the
 * triggerCancel function is called.
 *
 * Example:
 * const cancelButtonRef = useRef<CancelButtonRef>(null);
 * <CancelButton ref={cancelButtonRef} onCancel={() => { ... }} />
 * cancelButtonRef.current?.triggerCancel();
 *
 */
export function CancelButton({
    ref,
    onCancel,
    ...props
}: {
    ref?: React.Ref<CancelButtonRef>;
    onCancel: () => void;
} & Omit<ButtonProps, 'onClick' | 'ref'>) {
    const timeoutRef = useRef<NodeJS.Timeout | null>(null);
    const intervalRef = useRef<NodeJS.Timeout | null>(null);
    const [isCancelling, setIsCancelling] = useState(false);
    const [remainingTime, setRemainingTime] = useState(0);

    const triggerCancel = (timerDuration: number = 0) => {
        if (timerDuration <= 0) {
            onCancel();
            return;
        }

        setIsCancelling(true);
        setRemainingTime(Math.ceil(timerDuration / 1000));

        // Update countdown every second
        intervalRef.current = setInterval(() => {
            setRemainingTime((prev) => {
                const next = prev - 1;
                return next <= 0 ? 0 : next;
            });
        }, 1000);

        // Execute cancel after timeout
        timeoutRef.current = setTimeout(() => {
            if (intervalRef.current) clearInterval(intervalRef.current);
            onCancel();
            setIsCancelling(false);
            setRemainingTime(0);
        }, timerDuration);
    };

    const cancelTimer = () => {
        if (timeoutRef.current) clearTimeout(timeoutRef.current);
        if (intervalRef.current) clearInterval(intervalRef.current);
        setIsCancelling(false);
        setRemainingTime(0);
    };

    useImperativeHandle(ref, () => ({
        cancel: onCancel,
        cancelWithTimer: triggerCancel,
    }));

    return (
        <Button
            onClick={() => {
                if (isCancelling) {
                    cancelTimer();
                } else {
                    onCancel();
                }
            }}
            startIcon={<XIcon />}
            // TODO: a class for animations would be useful
            {...props}
        >
            {isCancelling ? `Cancelling in ${remainingTime}s...` : 'Cancel'}
        </Button>
    );
}
