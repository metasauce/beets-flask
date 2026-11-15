import { Action } from '@/api/config';
import { assertUnreachable } from '@/components/common/debugging/typing';

export function getActionDescription(action: Action | Action['name']): string {
    const name = typeof action === 'string' ? action : action.name;
    switch (name) {
        case 'retag':
            return 'Retag the selected album(s) this includes fetching candidates from your configured metadata sources.';
        case 'undo':
            return 'Allows you to undo imports, this will remove the imported album(s) from your library.';
        case 'upload':
            return 'Open an overlay to select files for upload into the current inbox.';
        case 'import_bootleg':
            return 'Import album without using a candidate, this is useful where online metadata is not available, such as bootlegs or dubs.';
        case 'import_best':
            return 'Import the best candidate for the selected album(s), this will use your configured metadata sources to find the best match.';
        case 'delete':
            return 'Delete the selected folders from your inbox.';
        case 'delete_imported_folders':
            return 'Delete all folders from the inbox that have been imported.';
        case 'copy_path':
            return 'Copy the path of the selected album(s) to the clipboard.';
        case 'import_terminal':
            return 'Import the selected album(s) using the terminal, this will open a terminal window and run the import command.';
        default:
            return assertUnreachable(name);
    }
}

export function getActionOptionDescription(option: string): string {
    switch (option) {
        case 'group_albums':
            return 'Group albums together when retagging, this will combine multiple albums into a single album if they are from the same artist and have similar titles.';
        case 'autotag':
            return 'Use autotagging to find metadata for the selected album(s), this will use your configured metadata sources to find the best match.';
        case 'delete_files':
            return 'Delete the files associated with the selected album(s) when undoing an import, this will remove the files from your library folder.';
        default:
            return '';
    }
}
