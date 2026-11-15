/** Status Updates
 *
 * Allows to invalidate data based on status updates from the server.
 *
 * We use a context which is wrapped around the app on are relatively
 * high level. This context provides the socket connection and allows
 * to invalidate and refetch queries by sending messages from the server.
 *
 */

import { createContext, useContext, useEffect } from 'react';
import { type QueryClient } from '@tanstack/react-query';

import { queryClient } from '@/api/common';
import { invalidateSession, statusQueryOptions } from '@/api/session';
import { StatusSocket } from '@/api/websocket';
import { FileSystemUpdate, FolderStatusUpdate } from '@/pythonTypes';

import useSocket from './useSocket';
interface StatusContextI {
    isConnected: boolean;
    socket: StatusSocket | null;
}

const StatusContext = createContext<StatusContextI | null>(null);

export function StatusContextProvider({
    children,
    client,
}: {
    children: React.ReactNode;
    client: QueryClient;
}) {
    const { socket, isConnected } = useSocket('status');

    useEffect(() => {
        if (!socket) return;

        function handleFolderStatusUpdate(updateData: FolderStatusUpdate) {
            console.log('FolderStatusUpdate', updateData);
            // Update the folder's status directly; further data (session state,
            // duplicates) is refetched via invalidation.
            queryClient.setQueryData<FolderStatusUpdate>(
                statusQueryOptions(updateData.hash, updateData.path).queryKey,
                updateData
            );

            invalidateSession(updateData.hash).catch(console.error);
        }

        async function handleFileSystemUpdate(updateData: FileSystemUpdate) {
            console.log('FileSystemUpdate', updateData);
            await queryClient.invalidateQueries({
                queryKey: ['inbox'],
            });
        }

        socket.on('folder_status_update', handleFolderStatusUpdate);
        socket.on('file_system_update', handleFileSystemUpdate);

        return () => {
            socket.off('folder_status_update', handleFolderStatusUpdate);
            socket.off('file_system_update', handleFileSystemUpdate);
        };
    }, [socket, client]);

    return (
        <StatusContext.Provider value={{ isConnected, socket }}>
            {children}
        </StatusContext.Provider>
    );
}

export function useStatusSocket() {
    const context = useContext(StatusContext);
    if (!context) {
        throw new Error(
            'useStatusSocket must be used within a StatusSocketContextProvider'
        );
    }
    return context;
}
