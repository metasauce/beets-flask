import type { SerializedException } from '@/pythonTypes';

/** Convert an unknown thrown value into a displayable exception.
 *
 * TanStack Router types route errors as `unknown`, so we cannot assume
 * that anything thrown is an `Error` instance.
 */
export function toSerializedException(error: unknown): SerializedException {
    if (error instanceof Error) {
        return {
            type: error.name,
            message: error.message,
            description: error.message,
            trace: error.stack,
        };
    }

    let message: string;
    try {
        message =
            typeof error === 'string'
                ? error
                : (JSON.stringify(error) ?? String(error));
    } catch {
        message = String(error);
    }

    return {
        type: 'UnknownError',
        message,
        description: message,
    };
}
