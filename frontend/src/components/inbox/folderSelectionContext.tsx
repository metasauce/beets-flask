import {
    createContext,
    useCallback,
    useContext,
    useMemo,
    useState,
} from 'react';

import { Archive, Folder } from '@/pythonTypes';

/* --------------------------------- Context -------------------------------- */
// Allows to trigger actions on a single or multiple folders

export interface FolderSelectionContext {
    nSelected: number;
    selected: {
        hashes: Array<Folder['hash']>;
        paths: Array<Folder['full_path']>;
    };
    toggleSelect(folder: Folder | Archive): void;
    isSelected(folder: Folder | Archive): boolean;
    deselectAll(): void;
}

const FoldersContext = createContext<FolderSelectionContext | null>(null);

export function useFolderSelectionContext() {
    const context = useContext(FoldersContext);
    if (!context) {
        throw new Error(
            'useFoldersContext must be used inside a FoldersProvider'
        );
    }
    return context;
}

export function FolderSelectionProvider({
    children,
}: {
    children: React.ReactNode;
}) {
    // we do not need to store the selected folders directly but can
    // derive them from their selected hashes and paths, this is more or less an id for folders
    const [selected, setSelected] = useState<{
        hashes: Folder['hash'][];
        paths: Folder['full_path'][];
    }>({ hashes: [], paths: [] });

    const toggleSelect = useCallback((folder: Folder | Archive) => {
        setSelected((selected) => {
            if (selected.hashes.includes(folder.hash)) {
                const idx = selected.hashes.indexOf(folder.hash);

                const newHashes = selected.hashes.filter((_, i) => i !== idx);
                const newPaths = selected.paths.filter((_, i) => i !== idx);

                return {
                    hashes: newHashes,
                    paths: newPaths,
                };
            } else {
                return {
                    hashes: [...selected.hashes, folder.hash],
                    paths: [...selected.paths, folder.full_path],
                };
            }
        });
    }, []);

    const isSelected = useCallback(
        (folder: Folder | Archive) => selected.hashes.includes(folder.hash),
        [selected]
    );

    const deselectAll = useCallback(
        () => setSelected({ hashes: [], paths: [] }),
        []
    );

    const nSelected = selected.hashes.length;

    // Stable value: consumers only re-render when the selection changes,
    // not whenever the provider's parent re-renders.
    const value = useMemo(
        () => ({
            nSelected,
            toggleSelect,
            isSelected,
            selected,
            deselectAll,
        }),
        [nSelected, toggleSelect, isSelected, selected, deselectAll]
    );

    return (
        <FoldersContext.Provider value={value}>
            {children}
        </FoldersContext.Provider>
    );
}
