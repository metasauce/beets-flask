import { Dispatch, SetStateAction, useEffect, useState } from 'react';
import { useLocation, useNavigate } from '@tanstack/react-router';

type UseQueryParamsStateReturnType<T> = [T, Dispatch<SetStateAction<T>>];

/**
 * Custom hook to manage state synchronized with a URL query parameter.
 *
 * @template T - The type of the state value.
 * @param {string} param - The name of the query parameter to synchronize with.
 * @param {T} initialState - The initial state value.
 * @returns {[T, React.Dispatch<React.SetStateAction<T>>]} - Returns a tuple containing the current state value and a function to update it.
 *
 * @example
 * const [value, setValue] = useQueryParamsState<string>("myParam", "default");
 *
 */
export default function useQueryParamsState(
    param: string,
    initialState: string | null
): UseQueryParamsStateReturnType<string | null> {
    const location = useLocation();
    const navigate = useNavigate();

    // initialize on mount to current url, or passed init state
    const [value, setValue] = useState<string | null>(() => {
        // Parse query parameter value from the URL
        const searchParams = new URLSearchParams(location.search);
        const paramValue = searchParams.get(param);

        return paramValue !== null
            ? decodeURIComponent(paramValue)
            : initialState;
    });

    // write to navbar, using navigate when the value changes
    useEffect(() => {
        const currentSearchParams = new URLSearchParams(window.location.search);

        // Update the query parameter with the current state value
        if (value !== null && value !== '') {
            currentSearchParams.set(param, encodeURIComponent(value));
        } else {
            // Remove the query parameter if the value is null or empty
            currentSearchParams.delete(param);
        }

        // Update the current URL is not different
        if (window.location.pathname === location.pathname) {
            navigate({
                // @ts-expect-error: Search is not defined as we do not set from and to in useNavigate!
                search: Object.fromEntries(currentSearchParams),
            }).catch(console.error);
        }
    }, [param, value, location.pathname, navigate]);

    return [value, setValue];
}
