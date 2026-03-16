import {
    AudioLinesIcon,
    BadgeAlertIcon,
    BotIcon,
    BrainIcon,
    CalendarIcon,
    CassetteTapeIcon,
    CheckIcon,
    ChevronsDownUpIcon,
    ChevronsUpDownIcon,
    CircleCheckBigIcon,
    CircleHelpIcon,
    ClockIcon,
    CopyIcon,
    Disc3Icon,
    FileIcon,
    FileMusicIcon,
    FlagIcon,
    FolderIcon,
    FolderOpen,
    GuitarIcon,
    HashIcon,
    HistoryIcon,
    HourglassIcon,
    Icon,
    InboxIcon,
    LayoutListIcon,
    ListChecksIcon,
    LucideProps,
    Mic2Icon,
    PackageIcon,
    RocketIcon,
    SearchXIcon,
    TagIcon,
    TagsIcon,
    Tally5Icon,
    TriangleAlertIcon,
    UserRoundIcon,
} from 'lucide-react';
import { sneaker } from '@lucide/lab';
import { CircularProgress, Tooltip, useTheme } from '@mui/material';

import { MinimalConfig } from '@/api/config';
import { FolderStatus, SerializedException } from '@/pythonTypes';

import { GrowingRipple } from './loading';

import { PairChanges } from '../import/candidates/diff';

/* ------------------------------- Base icons ------------------------------- */

export function AlbumIcon(props: LucideProps) {
    return <Disc3Icon {...props} />;
}
export function ArtistIcon(props: LucideProps) {
    return <UserRoundIcon {...props} />;
}
export function TrackIcon(props: LucideProps) {
    return <AudioLinesIcon {...props} />;
}
export function AudioFileIcon(props: LucideProps) {
    return <FileMusicIcon {...props} />;
}
export function GenreIcon(props: LucideProps) {
    return <GuitarIcon {...props} />;
}
export function DurationIcon(props: LucideProps) {
    return <ClockIcon {...props} />;
}

/* -------------------------------------------------------------------------- */

/** Icon to show a folder, shows a disc icon if the folder is an album.
 *
 * isAlbum: if the folder is an album
 * isOpen: if the folder is open
 */
export function FolderTypeIcon({
    isAlbum,
    isOpen,
    isArchive = false,
    ...props
}: { isAlbum: boolean; isOpen: boolean; isArchive?: boolean } & LucideProps) {
    if (isArchive) {
        return <PackageIcon {...props} />;
    }

    if (isAlbum) {
        return (
            <AlbumIcon
                style={{
                    transform: isOpen ? 'rotate(90deg)' : '',
                    transition: 'transform 0.15s ease-in-out',
                    flexShrink: 0,
                }}
                {...props}
            />
        );
    } else {
        if (isOpen) {
            return <FolderOpen {...props} />;
        }
        return <FolderIcon {...props} />;
    }
}

/** Icon to show different file types.
 *
 * type: file type to show icon for (normally the ending of the file)
 */
export function FileTypeIcon({
    type,
    ...props
}: { type: string | undefined } & LucideProps) {
    switch (type) {
        case 'mp3':
        case 'flac':
        case 'wav':
        case 'ogg':
            return <FileMusicIcon {...props} />;
        default:
            return <FileIcon {...props} />;
    }
}

/** Icon to show different penalty types.
 */
export function PenaltyTypeIcon({
    type,
    ...props
}: { type: string } & LucideProps) {
    switch (type) {
        case 'artist':
            return <ArtistIcon {...props} />;
        case 'album':
            return <AlbumIcon {...props} />;
        case 'tracks':
        case 'track':
        case 'track_changes':
            return <TrackIcon {...props} />;
        case 'extra_tracks':
        case 'extra_track':
            return <ExtraTrack {...props} />;
        case 'extra_items':
        case 'extra_item':
            return <ExtraItem {...props} />;
        case 'media':
            return <CassetteTapeIcon {...props} />;
        case 'mediums':
            return <Tally5Icon {...props} />;
        case 'country':
            return <FlagIcon {...props} />;
        case 'year':
            return <CalendarIcon {...props} />;
        case 'duplicate':
            return <CopyIcon {...props} />;
        case 'label':
            return <Mic2Icon {...props} />;
        case 'catalognum':
            return <HashIcon {...props} />;
        default:
            console.warn(`Unknown penalty kind: ${type}`);
            return null;
    }
}

/** Icon to show different source types.
 *
 * Source types are the source of a match e.g. spotify.
 */
export function SourceTypeIcon({
    type,
    ...props
}: { type: string } & LucideProps) {
    switch (type.toLowerCase()) {
        case 'spotify':
            return <Spotify {...props} />;
        case 'mb':
        case 'musicbrainz':
            return <BrainIcon {...props} />;
        case 'aisauce':
            return <BotIcon {...props} />;
        case 'asis':
            return <FileMusicIcon {...props} />;
        default:
            console.warn(`Unknown source type: ${type}`);
            return <BadgeAlertIcon {...props} />;
    }
}

export function SourceTypeIconWithTooltip({
    type,
    ...props
}: { type: string } & LucideProps) {
    return (
        <Tooltip title={type === 'asis' ? 'Metadata from files' : type}>
            <SourceTypeIcon type={type} {...props} />
        </Tooltip>
    );
}

/** Shows the status of a folder */
export function FolderStatusIcon({
    status,
    exception,
    ...props
}: {
    status: FolderStatus;
    exception?: SerializedException | null;
    size?: number;
} & LucideProps) {
    switch (status) {
        case FolderStatus.UNKNOWN:
            return <CircleHelpIcon {...props} />;
        case FolderStatus.FAILED:
            if (exception && exception.type === 'NoCandidatesFoundException') {
                return <SearchXIcon {...props} />;
            }
            return <TriangleAlertIcon {...props} />;
        case FolderStatus.NOT_STARTED:
            return <HourglassIcon {...props} />;
        case FolderStatus.PENDING:
            return <GrowingRipple size={props.size} color={props.color} />;
        case FolderStatus.PREVIEWING:
            return (
                <CircularProgress
                    size={props.size}
                    sx={{
                        color: props.color || 'inherit',
                    }}
                />
            );
        case FolderStatus.IMPORTING:
            return (
                <CircularProgress
                    size={props.size}
                    sx={{
                        color: props.color || 'inherit',
                    }}
                    disableShrink
                />
            );
        case FolderStatus.PREVIEWED:
            return <TagsIcon {...props} />;
        case FolderStatus.IMPORTED:
            return (
                <CircleCheckBigIcon
                    {...props}
                    size={props.size ? props.size - 2 : undefined}
                />
            );
        case FolderStatus.DELETING:
        case FolderStatus.DELETED:
            return <HistoryIcon {...props} />;
        default:
            return <CircleHelpIcon {...props} />;
    }
}

// Manually edited spotify svg icon (removing the circle)
function Spotify(props: LucideProps) {
    return (
        <svg
            width={props.size || 24}
            height={props.size || 24}
            viewBox={`-1 0 18 18`}
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            version="1.1"
            {...props}
        >
            <path
                stroke="none"
                d="M 0,0 H 24 V 24 H 0 Z"
                fill="none"
                id="path2"
            />
            <g transform="translate(-4.3029676,-7.9256576)" id="g1349">
                <g id="g1196" transform="translate(0.03227154,1.7049163)">
                    <path
                        d="m 6.3949311,14.46672 c 3.7367129,-2.201671 8.2207679,-1.454328 11.2101379,0.7877"
                        id="path6"
                    />
                    <path
                        d="m 8.263287,18.991132 c 2.242028,-1.494685 5.978741,-1.494685 7.473426,0.747343"
                        id="path8"
                    />
                    <path
                        d="M 4.5265745,10.023022 C 7.5159444,8.5283366 13.494685,7.0336515 19.473425,10.770364"
                        id="path10"
                    />
                </g>
            </g>
        </svg>
    );
}

// Online-Globe with questionmark
function ExtraItem(props: LucideProps) {
    return (
        <svg
            width={props.size || 24}
            height={props.size || 24}
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            viewBox="0 0 24 24"
            strokeLinecap="round"
            strokeLinejoin="round"
            version="1.1"
            {...props}
        >
            <g transform="matrix(1,0,0,1,-1729,0)">
                <g
                    id="id112"
                    transform="matrix(0.615385,0,0,0.615385,666.231,4.30769)"
                >
                    <g transform="matrix(1,0,0,1,-8.10543,-10.4)">
                        <g transform="matrix(1.625,0,0,1.625,-1028.54,-1911.11)">
                            <g transform="matrix(1,0,0,1,1700.35,1178.15)">
                                <path d="M18,15.28c0.2,-0.4 0.5,-0.8 0.9,-1c0.85,-0.491 1.937,-0.324 2.6,0.4c0.3,0.4 0.5,0.8 0.5,1.3c0,1.3 -2,2 -2,2" />
                            </g>
                            <g transform="matrix(1,0,0,1,1700.35,1178.15)">
                                <path d="M20,22l0,0.01" />
                            </g>
                        </g>
                        <g transform="matrix(1.625,0,0,1.625,1735.19,3.4)">
                            <path d="M15.534,21.357c-1.099,0.415 -2.29,0.643 -3.534,0.643c-5.519,0 -10,-4.481 -10,-10c0,-5.519 4.481,-10 10,-10c5.033,0 9.203,3.726 9.898,8.568" />
                        </g>
                        <g transform="matrix(1.625,0,0,1.625,1735.19,3.4)">
                            <path d="M12,2c-5.302,5.567 -5.302,14.433 0,20" />
                        </g>
                        <g transform="matrix(1.625,0,0,1.625,1735.19,3.4)">
                            <path d="M15.879,10.308c-0.35,-3.026 -1.643,-5.96 -3.879,-8.308" />
                        </g>
                        <g transform="matrix(1.625,0,0,1.625,1735.19,3.4)">
                            <path d="M2,12l11.988,0" />
                        </g>
                    </g>
                </g>
            </g>
        </svg>
    );
}

// Hard-Drive with questionmark
function ExtraTrack(props: LucideProps) {
    return (
        <svg
            width={props.size || 24}
            height={props.size || 24}
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            viewBox="0 0 24 24"
            strokeLinecap="round"
            strokeLinejoin="round"
            version="1.1"
            {...props}
        >
            <g transform="matrix(1,0,0,1,-1672.14,-2.6)">
                <g
                    id="id11231"
                    transform="matrix(0.0995851,0,0,0.0995851,1566.98,94.1187)"
                >
                    <g transform="matrix(10.0417,0,0,10.0417,-15734.6,-949.125)">
                        <g transform="matrix(1,0,0,1,-27.9809,-1176.16)">
                            <g transform="matrix(1,0,0,1,1700.35,1178.15)">
                                <path d="M18,15.28c0.2,-0.4 0.5,-0.8 0.9,-1c0.85,-0.491 1.937,-0.324 2.6,0.4c0.3,0.4 0.5,0.8 0.5,1.3c0,1.3 -2,2 -2,2" />
                            </g>
                            <g transform="matrix(1,0,0,1,1700.35,1178.15)">
                                <path d="M20,22l0,0.01" />
                            </g>
                        </g>
                        <g transform="matrix(0.65,0,0,1,1672.51,2)">
                            <path d="M23.538,12l-21.538,0" />
                        </g>
                        <g transform="matrix(1,0,0,1,1671.81,2)">
                            <path d="M21.061,10.124l-2.511,-5.014c-0.337,-0.679 -1.032,-1.11 -1.79,-1.11l-9.52,0c-0.758,0 -1.453,0.431 -1.79,1.11l-3.45,6.89l-0,6c-0,1.097 0.903,2 2,2l12,0" />
                        </g>
                        <g transform="matrix(1,0,0,1,1671.81,2)">
                            <path d="M6,16l0.01,0" />
                        </g>
                        <g transform="matrix(1,0,0,1,1671.81,2)">
                            <path d="M10,16l0.01,0" />
                        </g>
                    </g>
                </g>
            </g>
        </svg>
    );
}

export function BootlegIcon(props: LucideProps) {
    return <Icon iconNode={sneaker} {...props} />;
}

export function InboxTypeIcon({
    type,
    ...props
}: {
    type?: MinimalConfig['gui']['inbox']['folders'][0]['autotag'];
} & LucideProps) {
    switch (type) {
        case 'bootleg':
            return <BootlegIcon {...props} />;
        case 'preview':
            return <TagIcon {...props} />;
        case 'auto':
            return <RocketIcon {...props} />;
    }
    return <InboxIcon {...props} />;
}

/** Icon to indicate the change to a track.
 *
 * This is used in mainly for the candidates diff view.
 */
export function ChangeIcon({
    type,
    ...props
}: {
    type?: PairChanges['changeType'];
} & LucideProps) {
    const theme = useTheme();

    props = {
        size: theme.iconSize.sm,
        ...props,
    };

    switch (type) {
        case 'extra_item':
            return <PenaltyTypeIcon type="extra_items" {...props} />;
        case 'extra_track':
            return <PenaltyTypeIcon type="extra_tracks" {...props} />;
        case 'change_minor':
        case 'change_major':
            return <PenaltyTypeIcon type="tracks" {...props} />;
        case 'no_change':
        default:
            return <CheckIcon {...props} />;
    }
}

/* ------------------------------- Selections ------------------------------- */

export function DeselectAllIcon(props: LucideProps) {
    return <LayoutListIcon {...props} />;
}

export function SelectAllIcon(props: LucideProps) {
    return <ListChecksIcon {...props} />;
}

export function CollapseAllIcon(props: LucideProps) {
    return <ChevronsDownUpIcon {...props} />;
}

export function ExpandAllIcon(props: LucideProps) {
    return <ChevronsUpDownIcon {...props} />;
}
