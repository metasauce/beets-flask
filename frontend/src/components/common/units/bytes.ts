export function humanizeBytes(bytes?: number | null): string {
    if (bytes === undefined || bytes === null || bytes < 0) return 'unknown';

    const units = ['bytes', 'kb', 'mb', 'gb', 'tb'];
    if (bytes === 0) return '0 bytes';

    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    const value = bytes / Math.pow(1024, i);

    return `${parseFloat(value.toFixed(1))} ${units[i]}`;
}
