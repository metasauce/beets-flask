/** API functions and hooks for the auth endpoints (i.e. /api_v1/auth). */

import {
    queryOptions,
    useMutation,
    UseMutationOptions,
    useQuery,
} from '@tanstack/react-query';

import { AuthFlow, AuthProviderStatus } from '@/pythonTypes';

import { APIError, queryClient } from './common';

/* -------------------------------- Queries -------------------------------- */

export const authProvidersQueryOptions = () =>
    queryOptions<AuthProviderStatus[], APIError>({
        queryKey: ['auth', 'providers'],
        queryFn: async () => {
            const response = await fetch('/auth/providers');
            return (await response.json()) as AuthProviderStatus[];
        },
    });

/** Returns the full query result; `data` is undefined while loading or on error. */
export const useAuthProviders = () => useQuery(authProvidersQueryOptions());

/* ------------------------------- Mutations ------------------------------- */

/** Start the PKCE flow: returns the URL to visit plus the single-use ``flow_id``. */
export const startAuthMutationOptions = (
    provider: string
): UseMutationOptions<AuthFlow, APIError, void> => ({
    mutationFn: async () => {
        const response = await fetch(`/auth/${provider}/url`);
        return (await response.json()) as AuthFlow;
    },
});

/** Combined PKCE flow hook: ``start`` returns url + ``flow_id``, ``complete`` finishes it. */
export const useAuth = (provider: string) => {
    const start = useMutation(startAuthMutationOptions(provider));
    const complete = useMutation(completeAuthMutationOptions(provider));
    return { start, complete };
};

/** Complete the flow: exchange the redirect URL for a token, then refresh the providers. */
export const completeAuthMutationOptions = (
    provider: string
): UseMutationOptions<
    { authenticated: boolean },
    APIError,
    { flow_id: string; redirect_url: string }
> => ({
    mutationFn: async ({ flow_id, redirect_url }) => {
        const response = await fetch(`/auth/${provider}/complete`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ flow_id, redirect_url }),
        });
        return (await response.json()) as { authenticated: boolean };
    },
    onSuccess: async () => {
        await queryClient.invalidateQueries({
            queryKey: ['auth', 'providers'],
        });
    },
});
