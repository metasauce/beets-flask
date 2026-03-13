export const parseApiDate = (value: unknown): Date | undefined => {
    if (value === null || value === undefined) {
        return undefined;
    }

    const numeric = typeof value === 'number' ? value : Number(value);
    if (!Number.isNaN(numeric)) {
        // Some API responses provide UNIX seconds while others use milliseconds.
        const timestamp = numeric < 1e12 ? numeric * 1000 : numeric;
        const date = new Date(timestamp);
        return Number.isNaN(date.getTime()) ? undefined : date;
    }

    if (typeof value === 'string') {
        const date = new Date(value);
        return Number.isNaN(date.getTime()) ? undefined : date;
    }

    return undefined;
};

export const relativeTime = (date?: Date | null) => {
    if (!date) return 'never';

    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);
    const months = Math.floor(days / 30);
    const years = Math.floor(months / 12);

    if (seconds < 60) {
        return `${seconds} second${seconds > 1 ? 's' : ''} ago`;
    } else if (minutes < 60) {
        return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
    } else if (hours < 24) {
        return `${hours} hour${hours > 1 ? 's' : ''} ago`;
    } else if (days < 30) {
        return `${days} day${days > 1 ? 's' : ''} ago`;
    } else if (months < 12) {
        return `${months} month${months > 1 ? 's' : ''} ago`;
    } else {
        return `${years} year${years > 1 ? 's' : ''} ago`;
    }
};

/** Humanize the duration in seconds to a human readable format.
 */
export const humanizeDuration = (duration: number) => {
    const seconds = Math.floor(duration % 60);
    const minutes = Math.floor((duration / 60) % 60);
    const hours = Math.floor((duration / 60 / 60) % 24);
    const days = Math.floor(duration / 60 / 60 / 24);

    const parts = [];

    if (days > 0) parts.push(`${days}d`);
    if (hours > 0) parts.push(`${hours}h`);
    if (minutes > 0) parts.push(`${minutes}m`);
    if (seconds > 0) parts.push(`${seconds}s`);
    if (parts.length === 0) return `${duration.toFixed(2)}s`;

    return parts.join(' ');
};

/**
 * Formats a Date object using Python-style format strings
 * @param date - The Date object to format
 * @param formatStr - Python-style format string (e.g. "%Y-%m-%d %H:%M:%S")
 * @returns Formatted date string
 */
export const formatDate = (date: Date, formatStr: string) => {
    const pad = (num: number) => num.toString().padStart(2, '0');

    const replacements: Record<string, string> = {
        '%Y': date.getFullYear().toString(), // Year (4 digits)
        '%y': date.getFullYear().toString().slice(-2), // Year (2 digits)
        '%m': pad(date.getMonth() + 1), // Month (01-12)
        '%d': pad(date.getDate()), // Day (01-31)
        '%H': pad(date.getHours()), // Hour (00-23)
        '%M': pad(date.getMinutes()), // Minute (00-59)
        '%S': pad(date.getSeconds()), // Second (00-59)
        '%A': [
            'Sunday',
            'Monday',
            'Tuesday',
            'Wednesday', // Full weekday name
            'Thursday',
            'Friday',
            'Saturday',
        ][date.getDay()],
        '%a': ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][date.getDay()], // Short weekday
        '%B': [
            'January',
            'February',
            'March',
            'April',
            'May', // Full month name
            'June',
            'July',
            'August',
            'September',
            'October',
            'November',
            'December',
        ][date.getMonth()],
        '%b': [
            'Jan',
            'Feb',
            'Mar',
            'Apr',
            'May',
            'Jun', // Short month name
            'Jul',
            'Aug',
            'Sep',
            'Oct',
            'Nov',
            'Dec',
        ][date.getMonth()],
        '%p': date.getHours() < 12 ? 'AM' : 'PM', // AM/PM
    };

    return formatStr.replace(
        /%[YymdHMSAaBb]/g,
        (match) => replacements[match] || match
    );
};

export function trackLength(length: number): {
    hours: number;
    minutes: number;
    seconds: number;
} {
    const hours = Math.floor(length / 3600);
    const minutes = Math.floor((length % 3600) / 60);
    const seconds = Math.floor(length % 60);

    return { hours, minutes, seconds };
}

/** Track length representation
 *
 * - (?:??) (if length is unknown)
 * - (00:00)
 * - (00h:00:00) (if hours > 0)
 *
 * brackets - if false it will return a string without brackets
 */
export const trackLengthRep = (length?: number | null, brackets = true) => {
    if (length === undefined || length === null) {
        return brackets ? '(?:??)' : '?:??';
    }
    const { hours, minutes, seconds } = trackLength(length);
    const s = `${hours ? `${hours}h ` : ''}${minutes}:${seconds.toString().padStart(2, '0')}`;
    return brackets ? `(${s})` : s;
};
