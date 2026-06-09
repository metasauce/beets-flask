import { Change } from 'diff';
import { ArrowRightIcon } from 'lucide-react';
import React, {
    createContext,
    ReactElement,
    ReactNode,
    useContext,
    useEffect,
    useMemo,
    useState,
} from 'react';
import {
    styled,
    SxProps,
    Theme,
    Tooltip,
    Typography,
    useTheme,
} from '@mui/material';
import Box, { BoxProps } from '@mui/material/Box';

import { useDiff } from '@/components/common/hooks/useDiff';
import { ChangeIcon } from '@/components/common/icons';
import { trackLengthRep } from '@/components/common/units/time';
import {
    ItemInfo,
    SerializedCandidateState,
    SerializedTaskState,
    TrackInfo,
} from '@/pythonTypes';

/* ------------------------------- Track Diff ------------------------------- */
// Basically a grid layout showing the changes to all tracks
// In theory we can compare two generic candidates but the current use is always against
// the asis candidate

const TrackChangesGrid = styled(Box)(({ theme }) => ({
    display: 'grid',
    width: 'min-content',
    gridTemplateColumns: `repeat(8, max-content)`,

    //Column gap
    '> * > *': {
        paddingInline: theme.spacing(0.75),
    },

    // On mobile the full layout stretches over 2 lines
    [theme.breakpoints.down('tablet')]: {
        gridTemplateColumns: `
            repeat(4, max-content)
        `,

        // Apply Margin to 2nd row in full layout,
        // this seperates the different items
        // we select the first 4 items i.e. [1] t1 ->
        '[data-full=true] > *:nth-of-type(-n+4)': {
            marginTop: theme.spacing(0.75),
        },
        '[data-full=true]:first-of-type > *': {
            marginTop: 0,
        },
    },
}));

export type PairChanges = {
    titleHasChanged: boolean;
    timeHasChanged: boolean;
    indexHasChanged: boolean;
    numChanges: number; // how many of the above components changed
    changeType?:
        | 'no_change'
        | 'change_minor'
        | 'change_major'
        | 'extra_track'
        | 'extra_item';
};

function didPairChange(
    from: TrackInfo | ItemInfo,
    to: TrackInfo | ItemInfo
): PairChanges {
    const changes = {
        titleHasChanged: from.title !== to.title,
        timeHasChanged: Math.abs((from.length || 0) - (to.length || 0)) > 5,
        indexHasChanged: from.index !== to.index,
    };
    return {
        ...changes,
        numChanges:
            Number(changes.titleHasChanged) +
            Number(changes.timeHasChanged) +
            Number(changes.indexHasChanged),
    };
}

const TrackDiffContext = createContext<{
    extra_items: ItemInfo[];
    extra_tracks: TrackInfo[];
    pairs: Array<[ItemInfo, TrackInfo, PairChanges]>;
    pairs_extended: Array<
        [ItemInfo | undefined, TrackInfo | undefined, PairChanges]
    >;
    candidate: SerializedCandidateState;
    items: SerializedTaskState['items'];
    nChanges: number;
} | null>(null);

/** Context provider precomputes
 * some common values for the track diff view
 * which we dont want to recompute.
 */
export function TrackDiffContextProvider({
    children,
    candidate,
    items,
}: {
    children: React.ReactNode;
    candidate: SerializedCandidateState;
    items: SerializedTaskState['items'];
}) {
    // Create Venn diagram
    // items ∩ tracks = pairs
    // items' ∩ tracks = extra_items
    // items ∩ tracks' = extra_tracks
    const { extra_items, extra_tracks, pairs, pairs_extended, nChanges } =
        useMemo(() => {
            const extra_items: ItemInfo[] = [];
            const extra_tracks: TrackInfo[] = [];
            const pairs: Array<[ItemInfo, TrackInfo, PairChanges]> = [];
            let pairs_extended: Array<
                [ItemInfo | undefined, TrackInfo | undefined, PairChanges]
            > = [];
            let nChanges = 0;

            // mapping is a dict of item_idx -> track_idx
            for (const item_idx in candidate.mapping) {
                const track_idx = candidate.mapping[item_idx];
                const item = items[item_idx];
                const track = candidate.tracks[track_idx];
                if (item && track) {
                    const change = didPairChange(item, track);
                    // change type needs more details, computed in trackdiffrow
                    pairs.push([item, track, change]);
                    nChanges += Number(change.numChanges > 0);
                } else {
                    console.warn(
                        `TrackDiffContextProvider: item ${item_idx} or track ${track_idx} not found`
                    );
                }
            }

            // FIXME: could be a bit more efficient with sets
            for (let i = 0; i < candidate.tracks.length; i++) {
                const track = candidate.tracks[i];
                if (!pairs.some(([, other]) => other.index === track.index)) {
                    extra_tracks.push(track);
                }
            }
            for (let i = 0; i < items.length; i++) {
                const item = items[i];
                if (!pairs.some(([other]) => other.index === item.index)) {
                    extra_items.push(item);
                }
            }

            pairs.sort((a, b) => {
                const a_idx = a[1].index ?? 0;
                const b_idx = b[1].index ?? 0;
                if (a_idx < b_idx) return -1;
                if (a_idx > b_idx) return 1;
                return 0;
            });

            // create a list of pairs_extended for all items - track combinations,
            // even where one side cannot be associated with the other.
            // then the missing side should just be undefined.
            // Add all matched pairs
            pairs_extended = structuredClone(pairs);
            extra_tracks.forEach((track) => {
                // we have the convention that missing items/tracks do not have literal
                // changes of title, time etc - this helps with lower-level code,
                // where we do string comparisons.
                const change = didPairChange(track, track);
                change.changeType = 'extra_track';
                pairs_extended.push([undefined, track, change]);
            });

            // Sort pairs_extended by canonical track order (right-hand side)
            // Pairs and extra tracks come first (ordered by track index), then extra items at the end
            pairs_extended.sort((a, b) => {
                const a_idx = a[1]!.index ?? 0;
                const b_idx = b[1]!.index ?? 0;
                if (a_idx < b_idx) return -1;
                if (a_idx > b_idx) return 1;
                return 0;
            });

            extra_items.forEach((item) => {
                const change = didPairChange(item, item);
                change.changeType = 'extra_item';
                pairs_extended.push([
                    item,
                    undefined,
                    didPairChange(item, item),
                ]);
            });

            return {
                extra_items,
                extra_tracks,
                pairs,
                pairs_extended,
                nChanges,
            };
        }, [items, candidate]);

    return (
        <TrackDiffContext.Provider
            value={{
                extra_items,
                extra_tracks,
                pairs,
                pairs_extended,
                candidate,
                items,
                nChanges,
            }}
        >
            {children}
        </TrackDiffContext.Provider>
    );
}

export function useTrackDiffContext() {
    const context = useContext(TrackDiffContext);
    if (!context) {
        throw new Error(
            'useTrackDiffContext must be used within a TrackDiffContextProvider'
        );
    }
    return context;
}

/** The track diff contains a variety of information.
 *
 * - TrackChanges, shows how items (on disk) are mapped to tracks (from the candidate).
 * - ExtraTracks, shows tracks that are not matched to any item (missing on disk).
 * - ExtraItems, shows items that are missing from the candidate (not found online).
 */
export function TrackDiffsAfterImport({
    items,
    candidate,
}: {
    items: SerializedTaskState['items'];
    candidate: SerializedCandidateState;
}) {
    const theme = useTheme();

    // Show all track changes, unmatched tracks and unmatched items
    return (
        <TrackDiffContextProvider candidate={candidate} items={items}>
            <Box
                sx={{
                    display: 'flex',
                    flexDirection: 'row',
                    alignItems: 'center',
                    fontSize: theme.typography.body1.fontSize,
                    lineHeight: 1.25,
                }}
            >
                <TrackChangesExtended />
            </Box>
        </TrackDiffContextProvider>
    );
}

export function ExtraTracks() {
    const { extra_tracks } = useTrackDiffContext();
    const theme = useTheme();
    if (extra_tracks.length === 0) {
        return null;
    }
    return (
        <Box
            sx={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
            }}
        >
            <Typography variant="body1" color="text.secondary" pb={1}>
                The following tracks are included in the candidate (found
                online) but could not be found on disk.
            </Typography>
            <TrackChangesGrid
                sx={{
                    color: theme.palette.diffs.extraTrack,
                }}
            >
                {extra_tracks.map((track, i) => (
                    <TrackRow key={i} to={track} color="inherit" />
                ))}
            </TrackChangesGrid>
        </Box>
    );
}

export function ExtraItems() {
    const { extra_items } = useTrackDiffContext();
    const theme = useTheme();
    if (extra_items.length === 0) {
        return null;
    }
    return (
        <Box
            sx={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
            }}
        >
            <Typography variant="body1" color="text.secondary" pb={1}>
                The following tracks are included in the folder (on disk) but
                could not be found in the candidates (online).
            </Typography>
            <TrackChangesGrid
                sx={{
                    color: theme.palette.diffs.extraItem,
                }}
            >
                {extra_items.map((item, i) => (
                    <TrackRow key={i} from={item} color="inherit" />
                ))}
            </TrackChangesGrid>
        </Box>
    );
}

/** Shows all track changes as a list/grid
 *
 * Appear as popup after clicking
 * has to be used inside a TrackDiffContextProvider
 */
export function TrackChanges() {
    const { pairs } = useTrackDiffContext();

    // force major change layout for all rows
    const [titleChange, setTitleChange] = useState(false);

    if (pairs.length === 0) {
        return null;
    }

    return (
        <Box
            sx={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
            }}
        >
            {/*Changes grid*/}
            <TrackChangesGrid>
                {pairs.map(([item, track, change], i) => (
                    <TrackChangesRow
                        key={i}
                        from={item}
                        to={track}
                        pairChanges={change}
                        forceMajorChange={titleChange}
                        setForceMajorChange={setTitleChange}
                    />
                ))}
            </TrackChangesGrid>
        </Box>
    );
}

export function NoChanges({
    type,
}: {
    type: 'track_changes' | 'extra_tracks' | 'extra_items';
}) {
    let text = 'No changes detected.';
    switch (type) {
        case 'track_changes':
            text = 'No track changes detected.';
            break;
        case 'extra_tracks':
            text = 'All tracks online present on disk.';
            break;
        case 'extra_items':
            text = 'All tracks on disk found online.';
            break;
    }
    return (
        <Box
            sx={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                textAlign: 'center',
            }}
        >
            <Typography
                variant="body1"
                color="text.secondary"
                fontSize={'1.1rem'}
            >
                {text}
                <br />
                Perfectly balanced, as all things should be.
            </Typography>
        </Box>
    );
}
/** Shows all track changes, including extra and missing
 *
 * used as a summary after import
 * has to be used inside a TrackDiffContextProvider
 */
export function TrackChangesExtended() {
    const { pairs, pairs_extended } = useTrackDiffContext();

    // create a list of pairs_extended for all items - track combinations, even where one side cannot be associated
    // with the other. then the missing side should just be undefined.

    if (pairs.length === 0) {
        return null;
    }

    return (
        <Box
            sx={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
            }}
        >
            {/*Changes grid*/}
            <TrackChangesGrid>
                {pairs_extended.map(([item, track, change], i) =>
                    item && track ? (
                        <TrackChangesRow
                            key={i}
                            from={item}
                            to={track}
                            pairChanges={change}
                            forceMajorChange={false}
                            colorizeChanges={true}
                        />
                    ) : (
                        <TrackRow
                            key={i}
                            from={item}
                            to={track}
                            pairChanges={change}
                            forceMajorChange={false}
                        />
                    )
                )}
            </TrackChangesGrid>
        </Box>
    );
}

interface GenericDetailsItemProps extends BoxProps {
    icon: ReactElement;
    children?: ReactNode;
    tooltip?: string | ReactNode;
    label?: ReactNode;
    sx?: SxProps<Theme>;
    iconColor?: string;
    labelColor?: string;
}

export function GenericDetailsItem({
    icon,
    children,
    tooltip,
    label,
    sx,
    iconColor,
    labelColor,
    onClick = undefined,
    ...props
}: GenericDetailsItemProps) {
    // Show tooltip on hover of label row
    let ToolTipComp = ({ children }: { children: ReactElement }) => (
        <>{children}</>
    );
    if (tooltip) {
        ToolTipComp = ({ children }: { children: ReactElement }) => (
            <Tooltip title={tooltip}>{children}</Tooltip>
        );
    }

    // label is string or number
    if ((label && typeof label === 'string') || typeof label === 'number') {
        label = (
            <Box
                component="span"
                sx={{
                    color: labelColor || 'inherit',
                    cursor: onClick !== undefined ? 'pointer' : 'inherit',
                }}
            >
                {label}
            </Box>
        );
    }

    if (!label) {
        label = <Box component="span">Unknown</Box>;
    }

    return (
        <Box
            sx={[
                {
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 0.5,
                },
                // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
                ...(Array.isArray(sx) ? sx : [sx]),
            ]}
            onClick={onClick}
            {...props}
        >
            {/*Heading/content row*/}
            <ToolTipComp>
                <Box display="flex" gap={1} alignItems="flex-start">
                    <Box
                        sx={(theme) => ({
                            display: 'flex',
                            justifyContent: 'flex-start',
                            alignItems: 'flex-start',

                            width: theme.iconSize.sm,
                            color: iconColor || 'inherit',
                        })}
                    >
                        {icon}
                    </Box>
                    {label}
                </Box>
            </ToolTipComp>
            {children}
        </Box>
    );
}

export function GenericDetailsItemWithDiff({
    from,
    to,
    icon,
    tooltip,
    children,
    sx,
}: {
    from?: string | null;
    to?: string | null;
    icon: ReactElement;
    tooltip?: string;
    children?: ReactNode;
    sx?: SxProps<Theme>;
}) {
    const { fromParts, toParts, diff } = useDiffParts(from, to);

    return (
        <GenericDetailsItem
            icon={icon}
            tooltip={tooltip}
            label={
                <StyledDiff
                    fromParts={fromParts}
                    toParts={toParts}
                    diff={diff}
                    threshold={0.8}
                />
            }
            iconColor={undefined}
            sx={sx}
        >
            {children}
        </GenericDetailsItem>
    );
}

/**
 * Wrapper around TrackChangesRow that handles undefined `from` or `to` values.
 * (indicating a missing item or missing track, respectively).
 *
 * we have the convention that missing items/tracks do not have literal
 * changes of title, time etc - this helps with lower-level code,
 * where we do string comparisons.
 */
function TrackRow({
    from,
    to,
    pairChanges,
    forceMajorChange,
    setForceMajorChange,
    color,
}: {
    from?: ItemInfo;
    to?: TrackInfo | ItemInfo;
    pairChanges?: PairChanges;
    forceMajorChange?: boolean;
    setForceMajorChange?: (value: boolean) => void;
    color?: string;
}) {
    const theme = useTheme();

    if (!from && !to) {
        // both are undefined, we cannot render anything
        return null;
    }

    let fixedFrom: ItemInfo;
    let fixedTo: ItemInfo | TrackInfo;
    let missingKind: 'item' | 'track';
    // simply map the missing item to the present one,
    // then no changes visible.
    if (!from) {
        fixedTo = to as TrackInfo;
        fixedFrom = to as ItemInfo;
        missingKind = 'item';
    } else {
        fixedTo = from;
        fixedFrom = from;
        missingKind = 'track';
    }

    if (!pairChanges) {
        pairChanges = didPairChange(fixedFrom, fixedTo);
        if (missingKind === 'item') {
            pairChanges.changeType = 'extra_track';
        } else if (missingKind === 'track') {
            pairChanges.changeType = 'extra_item';
        }
    }

    color =
        color ||
        (missingKind === 'item'
            ? theme.palette.diffs.extraTrackLight
            : theme.palette.diffs.extraItemLight);

    return (
        <TrackChangesRow
            from={fixedFrom}
            to={fixedTo}
            pairChanges={pairChanges}
            forceMajorChange={forceMajorChange}
            setForceMajorChange={setForceMajorChange}
            colorizeChanges={false}
            sx={{
                color,
            }}
        />
    );
}

function TrackChangesRow({
    from,
    to,
    pairChanges,
    forceMajorChange = false,
    setForceMajorChange = () => {},
    colorizeChanges = true,
    sx = {},
}: {
    from: ItemInfo;
    to: TrackInfo | ItemInfo;
    pairChanges?: PairChanges;
    // HACK: React-Anti-Pattern: we do a computation in each row that we need to set
    // the state of all rows
    forceMajorChange?: boolean;
    setForceMajorChange?: (value: boolean) => void;
    colorizeChanges?: boolean;
    sx?: SxProps<Theme>;
}) {
    // FIXME: the backend types seem wrong, why optional?
    const theme = useTheme();

    const { fromParts, toParts, diff } = useDiffParts(
        from.title || '',
        to.title || ''
    );

    const fromD = {
        time: trackLengthRep(from.length),
        idx: from.index ?? 0,
        data: fromParts,
        type: 'from',
    };
    const toD = {
        time: trackLengthRep(to.length),
        idx: to.index ?? 0,
        data: toParts,
        type: 'to',
    };

    pairChanges = pairChanges || didPairChange(from, to);

    const hasChanges =
        pairChanges.titleHasChanged ||
        pairChanges.timeHasChanged ||
        pairChanges.indexHasChanged;

    // update change_type
    // TODO: think about how and where to differentiate major/minor on
    // higher-level components or context.
    if (hasChanges) {
        pairChanges.changeType = 'change_minor';
    } else {
        pairChanges.changeType = pairChanges.changeType || 'no_change';
    }

    /* ---------------------------- Major changes --------------------------- */

    // TODO: this is a bit harder to move to the context. we do not want to
    // compute the text-level diff for each row twice (probably expensive)
    // depending on the number of changes we render a slightly different row
    // major change shows changes with arrow i.e. [1] t1 -> [2] t2
    useEffect(() => {
        // if there is a major change in the title, we force the major change layout
        // for all rows
        if (pairChanges.titleHasChanged) {
            //Count changed chars vs unchanged
            let total = 0;
            let changed = 0;
            for (let i = 0; i < diff.length; i++) {
                const part = diff[i];
                total += part.count ?? 0;
                if (part.added || part.removed) {
                    changed += part.count ?? 0;
                }
            }
            // If the change is more than 75% we consider it a major change
            // otherwise we consider it a minor change
            if (changed / total > 0.75) {
                setForceMajorChange(true);
            }
        }
    }, [pairChanges.titleHasChanged, diff, setForceMajorChange]);

    const sx_clr_classes = {
        '.diffclr_added': {
            color: colorizeChanges
                ? hasChanges
                    ? theme.palette.diffs.added
                    : theme.palette.diffs.light
                : 'inherit',
        },
        '.diffclr_removed': {
            color: colorizeChanges
                ? hasChanges
                    ? theme.palette.diffs.removed
                    : theme.palette.diffs.light
                : 'inherit',
        },
        '.diffclr_changed': {
            color: colorizeChanges
                ? hasChanges
                    ? theme.palette.diffs.changed
                    : theme.palette.diffs.light
                : 'inherit',
        },
        '.diffclr_light': {
            color: colorizeChanges
                ? hasChanges
                    ? theme.palette.diffs.light
                    : theme.palette.diffs.light
                : 'inherit',
        },
        '.diffclr_inherit': {
            color: 'inherit',
        },
    };

    if (forceMajorChange) {
        return (
            <Box
                sx={{ ...sx, ...sx_clr_classes, display: 'contents' }}
                data-full={true}
            >
                {/* index */}
                <Box
                    sx={{
                        justifyContent: 'flex-end',
                        textAlign: 'right',
                    }}
                    className={
                        pairChanges.titleHasChanged
                            ? 'diffclr_removed'
                            : 'diffclr_light'
                    }
                >
                    {fromD.idx}
                </Box>

                {/* title and time */}
                <Box
                    className={
                        pairChanges.titleHasChanged
                            ? 'diffclr_removed'
                            : 'diffclr_light'
                    }
                >
                    {fromD.data}
                </Box>
                <Box
                    sx={{
                        display: 'flex',
                        justifyContent: 'flex-begin',
                    }}
                    className={
                        pairChanges.timeHasChanged
                            ? 'diffclr_removed'
                            : 'diffclr_light'
                    }
                >
                    {fromD.time}
                </Box>

                {/* change arrow */}
                <Box
                    sx={{
                        paddingInline: 1,
                        display: 'flex',
                        justifyContent: 'center',
                        alignItems: 'center',
                    }}
                >
                    <ArrowRightIcon
                        size={theme.iconSize.sm}
                        className="diffclr_changed"
                    />
                </Box>

                {/* index */}
                <Box
                    sx={{
                        textAlign: 'right',
                    }}
                    className={
                        pairChanges.titleHasChanged
                            ? 'diffclr_added'
                            : 'diffclr_light'
                    }
                >
                    {toD.idx}
                </Box>

                {/* title and time */}
                <Box
                    className={
                        pairChanges.titleHasChanged
                            ? 'diffclr_added'
                            : 'diffclr_light'
                    }
                >
                    {toD.data}
                </Box>
                <Box
                    sx={{
                        justifyContent: 'flex-end',
                        display: 'flex',
                    }}
                    className={
                        pairChanges.timeHasChanged
                            ? 'diffclr_added'
                            : 'diffclr_light'
                    }
                >
                    {toD.time}
                </Box>
                {/* Icon indicating which type of change (extra item...) */}
                <Box
                    sx={{ display: 'flex', alignItems: 'center' }}
                    className="diffclr_light"
                >
                    <ChangeIcon type={pairChanges.changeType} />
                </Box>
            </Box>
        );
    }

    /* ---------------------------- Minor changes --------------------------- */

    // Minor changes show only the changed title or change value
    // i.e. [1] t1 -> t2
    // or [1] -> [2] t1
    // no changes
    return (
        <Box
            sx={{
                ...sx,
                ...sx_clr_classes,
                display: 'grid',
                gridColumn: '1 / -1',
                gridTemplateColumns: 'subgrid',
            }}
        >
            {/* index */}
            <Box
                sx={{
                    textAlign: 'right',
                    display: 'grid',
                    gap: 0.5,
                    justifyContent: 'flex-end',
                    // Dynamically set the subgrid if there is a index change
                    // this aligns the indexs
                    //        [2]
                    // [2] -> [3]
                    gridTemplateColumns: pairChanges.indexHasChanged
                        ? '1fr auto 1fr'
                        : 'auto',
                    alignItems: 'center',
                }}
            >
                {pairChanges.indexHasChanged && (
                    <>
                        <Box
                            sx={{
                                textAlign: 'right',
                            }}
                            className="diffclr_removed"
                        >
                            {fromD.idx}
                        </Box>
                        <ArrowRightIcon
                            size={theme.iconSize.sm}
                            className="diffclr_changed"
                        />
                    </>
                )}
                <Box
                    className={
                        pairChanges.indexHasChanged
                            ? 'diffclr_added'
                            : 'diffclr_light'
                    }
                >
                    {toD.idx}
                </Box>
            </Box>

            {/*Title has no changes in minimal*/}
            <Box
                sx={{
                    textAlign: 'right',
                    display: 'flex',
                }}
                className={
                    pairChanges.titleHasChanged
                        ? 'diffclr_inherit'
                        : 'diffclr_light'
                }
            >
                {diff.map((part, index) => (
                    <Box
                        key={index}
                        sx={{
                            textDecoration: part.removed
                                ? 'line-through'
                                : 'none',
                        }}
                        className={
                            part.added
                                ? 'diffclr_added'
                                : part.removed
                                  ? 'diffclr_removed'
                                  : 'diffclr_inherit'
                        }
                        component="span"
                    >
                        {part.value}
                    </Box>
                ))}
            </Box>

            {/* Length might have changed */}
            <Box
                sx={{
                    textAlign: 'right',
                    display: 'grid',
                    gap: 0.5,
                    justifyContent: 'flex-end',
                    gridTemplateColumns: pairChanges.timeHasChanged
                        ? '1fr auto 1fr'
                        : 'auto',
                    alignItems: 'center',
                }}
            >
                {pairChanges.timeHasChanged && (
                    <>
                        <Box
                            sx={{
                                textAlign: 'right',
                            }}
                            className="diffclr_removed"
                        >
                            {fromD.time}
                        </Box>
                        <ArrowRightIcon
                            size={theme.iconSize.sm}
                            className="diffclr_changed"
                        />
                    </>
                )}
                <Box
                    sx={{
                        textAlign: 'right',
                    }}
                    className={
                        pairChanges.timeHasChanged
                            ? 'diffclr_added'
                            : 'diffclr_light'
                    }
                >
                    {toD.time}
                </Box>
            </Box>

            {/* Icon indicating which type of change (extra item...) */}
            <Box
                sx={{ display: 'flex', alignItems: 'center' }}
                className="diffclr_light"
            >
                <ChangeIcon type={pairChanges.changeType} />
            </Box>
        </Box>
    );
}

/* ------------------------------ Generic Diff ------------------------------ */

function useDiffParts(
    from?: string | null,
    to?: string | null,
    method?: 'chars' | 'words' | 'wordsWithSpace' | 'full' | 'auto'
) {
    const diff = useDiff(from, to, method);

    // Construct a from and to element
    const fromParts: React.ReactNode[] = [];
    const toParts: React.ReactNode[] = [];

    let hasAdded = false;
    let hasRemoved = false;

    diff.forEach((part, index) => {
        const span = (
            <Box key={index} component="span">
                {part.value}
            </Box>
        );

        if (part.added) {
            toParts.push(span);
            hasAdded = true;
        } else if (part.removed) {
            fromParts.push(span);
            hasRemoved = true;
        } else {
            fromParts.push(span);
            toParts.push(span);
        }
    });

    return { fromParts, toParts, hasAdded, hasRemoved, diff };
}

export function GenericDiff({
    from,
    to,
    method,
    icon,
}: {
    from?: string | null;
    to: string;
    method?: 'chars' | 'words' | 'wordsWithSpace' | 'full' | 'auto';
    icon?: React.ReactNode;
}) {
    if (!from) {
        from = '';
    }

    const { fromParts, toParts, hasAdded, hasRemoved, diff } = useDiffParts(
        from,
        to,
        method
    );

    return (
        <Box
            sx={{
                display: 'flex',
                flexDirection: 'row',
                gap: 0.5,
                alignItems: 'center',
            }}
        >
            <Box
                sx={(theme) => ({
                    color:
                        hasAdded || hasRemoved
                            ? theme.palette.diffs.changed
                            : theme.palette.text.primary,
                    display: 'flex',
                    justifyContent: 'center',
                    alignItems: 'center',

                    // Define the size of the icon
                    ' > *': {
                        width: theme.iconSize.sm,
                        height: theme.iconSize.sm,
                    },
                })}
            >
                {icon}
            </Box>
            <StyledDiff
                fromParts={fromParts}
                toParts={toParts}
                diff={diff}
                threshold={0.8}
            />
        </Box>
    );
}

/** Simple string styling and diffing of two strings.
 *
 * Very similar to git diff. If the two strings are very different
 * it will show the diff as a single line with an arrow in between.
 *
 * Usage:
 * ```
 * const { fromParts, toParts, diff } = useDiffParts(from, to);
 * <StyledDiff from={fromParts} to={toParts} diff={diff} />
 */
export function StyledDiff({
    fromParts,
    toParts,
    diff,
    threshold = 0.8,
    ...props
}: {
    fromParts: ReactNode[];
    toParts: ReactNode[];
    diff: Change[];
    threshold?: number;
} & BoxProps) {
    const theme = useTheme();

    const majorChange = useMemo(() => {
        //Count changed chars vs unchanged
        //FIXME: This should be a generic function and not copy pasted
        let total = 0;
        let changed = 0;
        for (let i = 0; i < diff.length; i++) {
            const part = diff[i];
            total += part.count ?? 0;
            if (part.added || part.removed) {
                changed += part.count ?? 0;
            }
        }

        return changed / total > threshold && diff.length > 1;
    }, [diff, threshold]);

    if (fromParts.length === 0 && toParts.length === 0) {
        return (
            <Box sx={{ lineHeight: 1.25 }} {...props}>
                Unknown
            </Box>
        );
    }

    return (
        <Box
            sx={{
                lineHeight: 1.25,
                display: 'flex',
                alignItems: 'center',
                gap: 0.5,
            }}
            {...props}
        >
            {majorChange && fromParts.length > 0 && toParts.length > 0 ? (
                <>
                    <Box
                        sx={(theme) => ({
                            color: theme.palette.diffs.removed,
                            textDecoration: 'line-through',
                        })}
                        component="span"
                    >
                        {fromParts}
                    </Box>
                    <ArrowRightIcon
                        size={theme.iconSize.sm}
                        color={theme.palette.diffs.changed}
                    />
                    <Box
                        sx={(theme) => ({
                            color: theme.palette.diffs.added,
                        })}
                        component="span"
                    >
                        {toParts}
                    </Box>
                </>
            ) : (
                diff.map((part, index) => (
                    <Box
                        key={index}
                        sx={(theme) => ({
                            color: part.added
                                ? theme.palette.diffs.added
                                : part.removed
                                  ? theme.palette.diffs.removed
                                  : 'inherit',

                            textDecoration: part.removed
                                ? 'line-through'
                                : 'none',
                        })}
                        component="span"
                    >
                        {part.value}
                    </Box>
                ))
            )}
        </Box>
    );
}
