import {
    BrainCircuit,
    CheckCircle2,
    ChevronDown,
    ChevronRight,
    Copy,
    Disc3Icon,
    Download,
    ExternalLink,
    HelpCircle,
    ListMusic,
    Send,
    TriangleAlert,
    Users,
    XCircle,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import {
    Autocomplete,
    Box,
    Button,
    Card,
    CardContent,
    Chip,
    CircularProgress,
    MenuItem,
    Paper,
    Select,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    TextField,
    Tooltip,
    Typography,
    useTheme,
} from '@mui/material';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { createFileRoute } from '@tanstack/react-router';

import { Album, albumsInfiniteQueryOptions, artUrl } from '@/api/library';
import {
    albumExistsQueryOptions,
    musicbrainzStatusQueryOptions,
    prepareReleaseQueryOptions,
} from '@/api/musicbrainz';
import { AlbumGridCard } from '@/components/common/browser/albums';
import { PageWrapper } from '@/components/common/page';
import { trackLengthRep } from '@/components/common/units/time';
import { CardHeader } from '@/components/frontpage/statsCard';
import {
    ArtistMatch,
    CountryOption,
    PreparedArtist,
    PreparedRelease,
    ReleaseData,
} from '@/pythonTypes';

export const Route = createFileRoute('/musicbrainz/')({
    component: RouteComponent,
});

function RouteComponent() {
    return (
        <PageWrapper
            sx={(theme) => ({
                display: 'flex',
                flexDirection: 'column',
                minHeight: '100%',
                alignItems: 'center',
                paddingTop: theme.spacing(1),
                paddingInline: theme.spacing(0.5),
                gap: 2,
                [theme.breakpoints.up('laptop')]: {
                    height: 'auto',
                    paddingTop: theme.spacing(2),
                    paddingInline: theme.spacing(1),
                },
            })}
        >
            <Header />
            <AlbumSelector />
        </PageWrapper>
    );
}

/** Page header with a link to the MusicBrainz release editor */
function Header() {
    const theme = useTheme();
    const { data: status } = useQuery(musicbrainzStatusQueryOptions());

    return (
        <Stack
            direction="row"
            alignItems="center"
            justifyContent="space-between"
            sx={{ width: '100%', flexWrap: 'wrap', gap: 1 }}
        >
            <Stack direction="row" alignItems="center" gap={1}>
                <BrainCircuit color={theme.palette.secondary.main} />
                <Typography variant="h6">MusicBrainz</Typography>
            </Stack>
            <Tooltip
                title={
                    'The MusicBrainz API cannot create releases. ' +
                    'This assistant prepares the album data, so you can add the ' +
                    'release at the MusicBrainz release editor.'
                }
            >
                <Button
                    component="a"
                    href={
                        status?.editor_url ??
                        'https://musicbrainz.org/release/add'
                    }
                    target="_blank"
                    rel="noreferrer"
                    variant="outlined"
                    endIcon={<ExternalLink size={16} />}
                    disabled={!status?.enabled}
                >
                    Open release editor
                </Button>
            </Tooltip>
        </Stack>
    );
}

/** Select an album from the library and show the prepared release */
function AlbumSelector() {
    const [selected, setSelected] = useState<Album<false, true> | null>(null);
    const [showAll, setShowAll] = useState(false);

    const queryAlbums = useInfiniteQuery(
        albumsInfiniteQueryOptions({ query: '' })
    );

    const albums = useMemo(
        () => queryAlbums.data?.albums ?? [],
        [queryAlbums.data]
    );

    return (
        <Stack sx={{ width: '100%' }} gap={2}>
            <AlbumList
                albums={albums}
                total={queryAlbums.data?.total ?? 0}
                selectedId={selected?.id}
                onSelect={setSelected}
                isPending={queryAlbums.isPending}
                isError={queryAlbums.isError}
                showAll={showAll}
                onToggleShowAll={() => setShowAll((prev) => !prev)}
                hasMore={queryAlbums.hasNextPage}
                isFetchingMore={queryAlbums.isFetchingNextPage}
                onLoadMore={() => void queryAlbums.fetchNextPage()}
            />

            {selected ? <PreparedView albumId={selected.id} /> : null}
        </Stack>
    );
}

/** Album picker styled like the library browse albums view */
function AlbumList({
    albums,
    total,
    selectedId,
    onSelect,
    isPending,
    isError,
    showAll,
    onToggleShowAll,
    hasMore,
    isFetchingMore,
    onLoadMore,
}: {
    albums: Album<false, true>[];
    total: number;
    selectedId?: number;
    onSelect: (album: Album<false, true>) => void;
    isPending: boolean;
    isError: boolean;
    showAll: boolean;
    onToggleShowAll: () => void;
    hasMore: boolean;
    isFetchingMore: boolean;
    onLoadMore: () => void;
}) {
    const visibleAlbums = showAll ? albums : albums.slice(0, 6);
    return (
        <Card sx={{ padding: 2, width: '100%', overflow: 'unset' }}>
            <CardHeader icon={<Disc3Icon size={36} />} size="large">
                <Typography variant="body1" color="text.secondary">
                    Albums{total > 0 ? ` (${total})` : ''}
                </Typography>
            </CardHeader>
            <CardContent
                sx={{
                    paddingInline: 1,
                    paddingTop: 2,
                    m: 0,
                    paddingBottom: '0 !important',
                }}
            >
                {isPending ? (
                    <Box
                        sx={{
                            display: 'flex',
                            justifyContent: 'center',
                            p: 3,
                        }}
                    >
                        <CircularProgress />
                    </Box>
                ) : isError ? (
                    <Box sx={{ p: 2 }}>
                        <Typography color="error">
                            Failed to load the album list.
                        </Typography>
                    </Box>
                ) : albums.length === 0 ? (
                    <Box sx={{ p: 2 }}>
                        <Typography color="text.secondary">
                            No albums found.
                        </Typography>
                    </Box>
                ) : (
                    <Box>
                        <Typography
                            variant="h5"
                            fontWeight={800}
                            letterSpacing={0.5}
                        >
                            Select an album
                        </Typography>
                        <Box
                            sx={{
                                display: 'grid',
                                gridTemplateColumns:
                                    'repeat(auto-fill, minmax(300px, 1fr))',
                                gridAutoRows: 'auto',
                                gap: 1,
                                paddingTop: 2.5,
                            }}
                        >
                            {visibleAlbums.map((album) => (
                                <AlbumExistsCard
                                    key={album.id}
                                    album={album}
                                    selected={album.id === selectedId}
                                    onSelect={onSelect}
                                />
                            ))}
                        </Box>
                        <Box
                            sx={(theme) => ({
                                paddingTop: 3,
                                display: 'flex',
                                gap: 2,
                                fontWeight: 600,
                                justifyContent: 'flex-end',
                                [theme.breakpoints.down('tablet')]: {
                                    '>*': {
                                        width: '100%',
                                    },
                                },
                            })}
                        >
                            {showAll && hasMore && (
                                <Button
                                    variant="outlined"
                                    size="large"
                                    onClick={onLoadMore}
                                    disabled={isFetchingMore}
                                    sx={{
                                        fontWeight: 600,
                                    }}
                                >
                                    {isFetchingMore
                                        ? 'Loading…'
                                        : 'Load more albums'}
                                </Button>
                            )}
                            <Button
                                variant={showAll ? 'outlined' : 'contained'}
                                endIcon={
                                    showAll ? <ChevronDown /> : <ChevronRight />
                                }
                                size="large"
                                onClick={onToggleShowAll}
                                sx={{
                                    fontWeight: 600,
                                }}
                            >
                                {showAll ? 'Show less' : 'All Albums'}
                            </Button>
                        </Box>
                    </Box>
                )}
            </CardContent>
        </Card>
    );
}

/** Album card that checks MusicBrainz when the stored MBID is missing.
 *
 * Albums imported through beets carry ``mb_albumid``. Albums submitted via
 * the release editor do not, so the server looks the release up by barcode
 * before showing the badge.
 */
function AlbumExistsCard({
    album,
    selected,
    onSelect,
}: {
    album: Album<false, true>;
    selected: boolean;
    onSelect: (album: Album<false, true>) => void;
}) {
    const { data } = useQuery(
        albumExistsQueryOptions(album.id, !album.mb_albumid)
    );
    const mbid = album.mb_albumid ?? data?.mbid ?? undefined;
    return (
        <AlbumGridCard
            album={album}
            mbid={mbid}
            selected={selected}
            onSelect={onSelect}
        />
    );
}

/** Show the prepared data for the given album */
function PreparedView({ albumId }: { albumId: number }) {
    const { data, isPending, isError, error } = useQuery(
        prepareReleaseQueryOptions(albumId)
    );

    if (isPending) {
        return (
            <Paper sx={{ p: 4, display: 'flex', justifyContent: 'center' }}>
                <CircularProgress />
            </Paper>
        );
    }

    if (isError || !data) {
        return (
            <Paper sx={{ p: 3 }}>
                <Typography color="error">
                    Failed to prepare the album:{' '}
                    {String(error?.message ?? error)}
                </Typography>
            </Paper>
        );
    }

    return <ReleaseDetails key={albumId} prepared={data} />;
}

function ReleaseDetails({ prepared }: { prepared: PreparedRelease }) {
    const [selectedMbid, setSelectedMbid] = useState<Record<string, string>>(
        {}
    );
    const [selectedMedia, setSelectedMedia] = useState<string>(
        prepared.release.media ?? prepared.default_media_format
    );
    const [selectedCountry, setSelectedCountry] = useState<string>(
        prepared.release.country ?? ''
    );
    const copyText = formatCopyText(
        prepared,
        selectedMbid,
        selectedMedia,
        selectedCountry
    );

    const handleCopy = async () => {
        try {
            await navigator.clipboard.writeText(copyText);
        } catch (e) {
            console.error('Failed to copy to clipboard', e);
        }
    };

    const selectMbid = (artistName: string, mbid: string) => {
        setSelectedMbid((prev) => ({ ...prev, [artistName]: mbid }));
    };

    return (
        <Stack gap={2}>
            <Stack
                direction="row"
                alignItems="center"
                justifyContent="space-between"
                sx={{ flexWrap: 'wrap', gap: 1 }}
            >
                <Typography variant="h6">
                    {prepared.release.albumartist} — {prepared.release.album}
                </Typography>
                <Stack direction="row" gap={1}>
                    <Button
                        variant="contained"
                        startIcon={<Send size={16} />}
                        onClick={() =>
                            openReleaseEditor(
                                prepared,
                                selectedMbid,
                                selectedMedia,
                                selectedCountry
                            )
                        }
                        disabled={
                            prepared.release_editor_fields.length === 0 ||
                            !selectedCountry
                        }
                    >
                        Open release editor (prefilled)
                    </Button>
                    <Button
                        variant="outlined"
                        startIcon={<Copy size={16} />}
                        onClick={handleCopy}
                    >
                        Copy prepared data
                    </Button>
                    <Tooltip title="Download the local cover art to attach it to the release after it is created">
                        <Button
                            variant="outlined"
                            startIcon={<Download size={16} />}
                            onClick={() => void downloadCoverArt(prepared)}
                        >
                            Download cover art
                        </Button>
                    </Tooltip>
                </Stack>
            </Stack>

            {prepared.artists.length > 0 && (
                <ArtistsBlock
                    prepared={prepared}
                    selectedMbid={selectedMbid}
                    onSelect={selectMbid}
                />
            )}

            <ReleaseCard
                release={prepared.release}
                flags={prepared.flags}
                media={selectedMedia}
                mediaFormats={prepared.media_formats}
                onMediaChange={setSelectedMedia}
                country={selectedCountry}
                countries={prepared.countries}
                onCountryChange={setSelectedCountry}
            />

            <EditorChecklist
                checklist={prepared.checklist}
                tracks={prepared.tracks}
            />
        </Stack>
    );
}

/** The origin (scheme + host) of the MusicBrainz editor URL */
function editorOrigin(prepared: PreparedRelease): string {
    try {
        return new URL(prepared.editor_url).origin;
    } catch {
        return 'https://musicbrainz.org';
    }
}

/** Detect the image extension from the magic bytes of a blob */
async function imageExtensionFromBlob(blob: Blob): Promise<string> {
    const bytes = new Uint8Array(await blob.slice(0, 16).arrayBuffer());
    if (bytes[0] === 0xff && bytes[1] === 0xd8) return 'jpg';
    if (
        bytes[0] === 0x89 &&
        bytes[1] === 0x50 &&
        bytes[2] === 0x4e &&
        bytes[3] === 0x47
    ) {
        return 'png';
    }
    if (bytes[0] === 0x47 && bytes[1] === 0x49 && bytes[2] === 0x46)
        return 'gif';
    if (bytes[8] === 0x57 && bytes[9] === 0x45 && bytes[10] === 0x42)
        return 'webp';
    return 'png';
}

/** Fetch the local cover art and trigger a real download of it */
async function downloadCoverArt(prepared: PreparedRelease) {
    const response = await fetch(artUrl('album', prepared.album_id));
    if (!response.ok) {
        console.error('Failed to download cover art', response.status);
        return;
    }
    const blob = await response.blob();
    const extension = await imageExtensionFromBlob(blob);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${prepared.release.albumartist} - ${prepared.release.album}.${extension}`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
}

/** Human-readable label for an artist search match */
function matchLabel(match: ArtistMatch): string {
    const parts = [match.name];
    if (match.disambiguation) {
        parts.push(match.disambiguation);
    }
    if (match.begin_date) {
        parts.push(match.begin_date);
    }
    if (match.type) {
        parts.push(match.type);
    }
    return parts.join(' · ');
}

const ARTIST_STATUS: Record<
    PreparedArtist['exists'],
    { text: string; color: string }
> = {
    yes: { text: 'On MusicBrainz', color: 'success.main' },
    maybe: { text: 'Matches found, verify', color: 'warning.main' },
    no: { text: 'Not on MusicBrainz', color: 'warning.main' },
    unknown: { text: 'Could not check MusicBrainz', color: 'text.disabled' },
};

const ARTIST_STATUS_ICON = {
    yes: CheckCircle2,
    maybe: HelpCircle,
    no: TriangleAlert,
    unknown: HelpCircle,
} as const;

function ArtistsBlock({
    prepared,
    selectedMbid,
    onSelect,
}: {
    prepared: PreparedRelease;
    selectedMbid: Record<string, string>;
    onSelect: (artistName: string, mbid: string) => void;
}) {
    return (
        <Card variant="outlined">
            <CardContent>
                <Stack
                    direction="row"
                    alignItems="center"
                    gap={1}
                    sx={{ mb: 1 }}
                >
                    <Users size={16} />
                    <Typography variant="subtitle2">Artists</Typography>
                </Stack>
                <Stack gap={1.5}>
                    {prepared.artists.map((artist) => (
                        <ArtistRow
                            key={artist.name}
                            artist={artist}
                            origin={editorOrigin(prepared)}
                            chosenMbid={
                                selectedMbid[artist.name] ?? artist.mbid ?? ''
                            }
                            onSelect={(mbid) => onSelect(artist.name, mbid)}
                        />
                    ))}
                </Stack>
            </CardContent>
        </Card>
    );
}

function ArtistRow({
    artist,
    origin,
    chosenMbid,
    onSelect,
}: {
    artist: PreparedArtist;
    origin: string;
    chosenMbid: string;
    onSelect: (mbid: string) => void;
}) {
    const status = ARTIST_STATUS[artist.exists];
    const StatusIcon = ARTIST_STATUS_ICON[artist.exists];
    const selectedMatch =
        artist.matches.find((m) => m.mbid === chosenMbid) ?? null;
    const storedOnly = chosenMbid !== '' && selectedMatch === null;
    const value: ArtistMatch | null =
        selectedMatch ??
        (storedOnly
            ? {
                  name: artist.name,
                  mbid: chosenMbid,
                  disambiguation: 'stored MBID from beets',
              }
            : null);

    return (
        <Box>
            <Stack direction="row" alignItems="flex-start" gap={1}>
                <StatusIcon
                    size={16}
                    color={status.color}
                    style={{ marginTop: 4 }}
                />
                <Stack flex={1} gap={0.5} minWidth={0}>
                    <Stack
                        direction="row"
                        alignItems="baseline"
                        flexWrap="wrap"
                        gap={1}
                    >
                        <Typography variant="body1" fontWeight="bold">
                            {artist.name}
                        </Typography>
                        {artist.sort_name && (
                            <Typography
                                variant="caption"
                                color="text.secondary"
                            >
                                ({artist.sort_name})
                            </Typography>
                        )}
                        <Typography variant="caption" color={status.color}>
                            {status.text}
                        </Typography>
                    </Stack>

                    {artist.matches.length > 0 ? (
                        <Autocomplete
                            size="small"
                            value={value}
                            options={artist.matches}
                            getOptionLabel={matchLabel}
                            isOptionEqualToValue={(a, b) => a.mbid === b.mbid}
                            onChange={(_e, match) =>
                                onSelect(match ? match.mbid : '')
                            }
                            renderInput={(params) => (
                                <TextField {...params} label="Artist match" />
                            )}
                        />
                    ) : (
                        <TextField
                            size="small"
                            label="Artist MBID"
                            placeholder="Paste an MBID (e.g. after creating the artist)"
                            value={chosenMbid}
                            onChange={(e) => onSelect(e.target.value.trim())}
                        />
                    )}

                    <Stack direction="row" gap={1} flexWrap="wrap">
                        {chosenMbid && (
                            <Button
                                component="a"
                                size="small"
                                variant="text"
                                href={`${origin}/artist/${chosenMbid}`}
                                target="_blank"
                                rel="noreferrer"
                                endIcon={<ExternalLink size={14} />}
                            >
                                View artist
                            </Button>
                        )}
                        {artist.create_url && artist.exists !== 'yes' && (
                            <Button
                                component="a"
                                size="small"
                                variant="outlined"
                                href={artist.create_url}
                                target="_blank"
                                rel="noreferrer"
                                endIcon={<ExternalLink size={14} />}
                            >
                                Create artist (prefilled)
                            </Button>
                        )}
                    </Stack>
                </Stack>
            </Stack>
        </Box>
    );
}

/** Release editor fields with the user's artist MBID selections applied */
function buildEditorFieldsWithSelection(
    prepared: PreparedRelease,
    selectedMbid: Record<string, string>
): Array<{ name: string; value: string }> {
    const fields = prepared.release_editor_fields.map((f) => ({ ...f }));
    const byName = new Map(fields.map((f) => [f.name, f]));
    const added: Array<{ name: string; value: string }> = [];

    const setField = (name: string, value: string) => {
        const existing = byName.get(name);
        if (existing) {
            existing.value = value;
        } else {
            const field = { name, value };
            byName.set(name, field);
            added.push(field);
        }
    };

    for (const artist of prepared.artists) {
        const chosen = selectedMbid[artist.name];
        if (!chosen) continue;
        const resolvedName =
            artist.matches.find((m) => m.mbid === chosen)?.name ?? artist.name;
        for (const mbidKey of artist.mbid_fields) {
            setField(mbidKey, chosen);
            setField(mbidKey.replace(/\.mbid$/, '.name'), resolvedName);
            setField(mbidKey.replace(/\.mbid$/, '.artist.name'), resolvedName);
        }
    }
    return [...fields, ...added];
}

/**
 * Submit the prepared data to the MusicBrainz release editor as a form POST.
 *
 * The editor seeds its fields from the POSTed body (see the `ReleaseEditor`
 * controller). The field names use the dotted `CGI::Expand` convention the
 * editor expects (e.g. `mediums.0.track.1.length`), so the release opens in a
 * new tab already prefilled. The form uses a regular HTML navigation, so it
 * works cross-origin (no CORS) as long as the user is logged in at
 * `editor_url`.
 */
/** Apply the format chosen in the UI to the seeded medium format fields */
function applyMediaOverride(
    fields: Array<{ name: string; value: string }>,
    media: string
): Array<{ name: string; value: string }> {
    return fields.map((field) =>
        /^mediums\.\d+\.format$/.test(field.name)
            ? { ...field, value: media }
            : field
    );
}

/** Add or replace the country field with the code chosen in the UI */
function applyCountryOverride(
    fields: Array<{ name: string; value: string }>,
    country: string
): Array<{ name: string; value: string }> {
    const code = country.trim().toUpperCase();
    if (!code) return fields;
    const existing = fields.find((field) => field.name === 'country');
    if (existing) {
        return fields.map((field) =>
            field.name === 'country' ? { ...field, value: code } : field
        );
    }
    return [...fields, { name: 'country', value: code }];
}

function openReleaseEditor(
    prepared: PreparedRelease,
    selectedMbid: Record<string, string>,
    media: string,
    country: string
) {
    const fields = applyCountryOverride(
        applyMediaOverride(
            buildEditorFieldsWithSelection(prepared, selectedMbid),
            media
        ),
        country
    );
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = prepared.editor_url;
    form.target = '_blank';
    form.rel = 'noreferrer';
    form.style.display = 'none';
    for (const field of fields) {
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = field.name;
        input.value = field.value;
        form.appendChild(input);
    }
    document.body.appendChild(form);
    form.submit();
    setTimeout(() => form.remove(), 0);
}

/** Warnings / info about the album */
function buildWarnings(flags: PreparedRelease['flags']): string[] {
    const warnings: string[] = [];
    if (!flags.on_musicbrainz) {
        warnings.push(
            'Album is not on MusicBrainz yet — it has to be created.'
        );
    }
    if (flags.multi_disc) {
        warnings.push('Multi-disc album, check disc numbers in the editor.');
    }
    if (flags.multi_artist) {
        warnings.push('Multiple artists detected, double check the artists.');
    }
    for (const key of flags.missing) {
        warnings.push(`Missing field: ${key}.`);
    }
    if (flags.missing_isrc.length > 0) {
        warnings.push(
            `No ISRC on ${flags.missing_isrc.length} track(s): ${flags.missing_isrc.join(', ')}.`
        );
    }
    if (flags.missing_track_artist.length > 0) {
        warnings.push(
            `No track artist on: ${flags.missing_track_artist.join(', ')}.`
        );
    }
    return warnings;
}

const RELEASE_FIELD_LABELS: Record<string, string> = {
    year: 'Year',
    label: 'Label',
    barcode: 'Barcode',
    catalognum: 'Catalog number',
    country: 'Country',
    disctotal: 'Discs',
    albumtype: 'Album type',
    genre: 'Genre',
    albumdisambig: 'Disambiguation',
};

/** Release level fields + warnings about the album */
function ReleaseCard({
    release,
    flags,
    media,
    mediaFormats,
    onMediaChange,
    country,
    countries,
    onCountryChange,
}: {
    release: ReleaseData;
    flags: PreparedRelease['flags'];
    media: string;
    mediaFormats: string[];
    onMediaChange: (media: string) => void;
    country: string;
    countries: CountryOption[];
    onCountryChange: (country: string) => void;
}) {
    const warnings = buildWarnings(flags);
    const entries = Object.entries(RELEASE_FIELD_LABELS)
        .filter(([key]) => key !== 'country')
        .map(([key, label]) => ({
            key,
            label,
            value: release[key as keyof ReleaseData],
        }))
        .filter(
            (e) => e.value !== undefined && e.value !== '' && e.value !== 0
        );

    const original = release.media_original;
    const mediaNote =
        original && media !== original
            ? `Adjusted from ${original} (library tag) — valid for ${release.year ?? '?'}.`
            : original && media === original
              ? `${original} is not valid for ${release.year ?? '?'} on MusicBrainz; change the format or the release date.`
              : null;

    return (
        <Card variant="outlined">
            <CardContent>
                <Typography variant="subtitle2" gutterBottom>
                    Release
                </Typography>
                {warnings.length > 0 ? (
                    <Stack gap={0.5} sx={{ mb: 1 }}>
                        {warnings.map((w) => (
                            <Stack
                                key={w}
                                direction="row"
                                gap={1}
                                alignItems="center"
                            >
                                <TriangleAlert size={16} color="warning.main" />
                                <Typography variant="body2">{w}</Typography>
                            </Stack>
                        ))}
                    </Stack>
                ) : (
                    <Chip
                        icon={<CheckCircle2 size={16} />}
                        label="All the usual fields are filled."
                        color="success"
                        variant="outlined"
                        size="small"
                        sx={{ mb: 1 }}
                    />
                )}
                <Box
                    sx={{
                        display: 'grid',
                        gridTemplateColumns: {
                            xs: '1fr',
                            sm: 'repeat(2, minmax(0, 1fr))',
                        },
                        gap: 1,
                    }}
                >
                    <Stack
                        direction="row"
                        justifyContent="space-between"
                        alignItems="center"
                        gap={1}
                        sx={{
                            borderBottom: '1px solid',
                            borderColor: 'divider',
                            pb: 0.5,
                        }}
                    >
                        <Typography variant="body2" color="text.secondary">
                            Format
                        </Typography>
                        <Select
                            size="small"
                            value={media}
                            onChange={(e) =>
                                onMediaChange(String(e.target.value))
                            }
                            sx={{ minWidth: 140 }}
                        >
                            {mediaFormats.map((f) => (
                                <MenuItem key={f} value={f}>
                                    {f}
                                </MenuItem>
                            ))}
                        </Select>
                    </Stack>
                    <Stack
                        direction="row"
                        justifyContent="space-between"
                        alignItems="center"
                        gap={1}
                        sx={{
                            borderBottom: '1px solid',
                            borderColor: 'divider',
                            pb: 0.5,
                        }}
                    >
                        <Typography variant="body2" color="text.secondary">
                            Country
                        </Typography>
                        <Select
                            size="small"
                            displayEmpty
                            value={country}
                            onChange={(e) =>
                                onCountryChange(String(e.target.value))
                            }
                            sx={{ minWidth: 140 }}
                        >
                            <MenuItem value="" disabled>
                                Select a country…
                            </MenuItem>
                            {countries.map((c) => (
                                <MenuItem key={c.code} value={c.code}>
                                    {c.name}
                                </MenuItem>
                            ))}
                        </Select>
                    </Stack>
                    {entries.map(({ key, label, value }) => (
                        <Stack
                            key={key}
                            direction="row"
                            justifyContent="space-between"
                            alignItems="baseline"
                            gap={1}
                            sx={{
                                borderBottom: '1px solid',
                                borderColor: 'divider',
                                pb: 0.5,
                            }}
                        >
                            <Typography variant="body2" color="text.secondary">
                                {label}
                            </Typography>
                            <Typography
                                variant="body2"
                                sx={{ textAlign: 'right' }}
                            >
                                {String(value)}
                            </Typography>
                        </Stack>
                    ))}
                </Box>
                {mediaNote && (
                    <Typography variant="caption" color="text.secondary">
                        {mediaNote}
                    </Typography>
                )}
            </CardContent>
        </Card>
    );
}

/** Groups of checklist keys, displayed as labeled columns */
const CHECKLIST_SECTIONS: Array<{
    title: string;
    keys: string[];
}> = [
    {
        title: 'Essentials',
        keys: ['title', 'artist', 'format', 'tracks', 'year'],
    },
    {
        title: 'Album details',
        keys: ['label', 'catalog', 'barcode', 'country'],
    },
    { title: 'Verify before submitting', keys: ['isrc', 'on_musicbrainz'] },
];

/** The MusicBrainz release editor checklist + the tracklist to check */
function EditorChecklist({
    checklist,
    tracks,
}: {
    checklist: PreparedRelease['checklist'];
    tracks: PreparedRelease['tracks'];
}) {
    const byKey = new Map(checklist.map((item) => [item.key, item]));

    return (
        <Card variant="outlined">
            <CardContent>
                <Typography variant="subtitle2" gutterBottom>
                    Release editor checklist
                </Typography>
                <Stack
                    direction="row"
                    gap={2}
                    flexWrap="wrap"
                    useFlexGap
                    sx={{ mb: 2 }}
                >
                    {CHECKLIST_SECTIONS.map((section) => {
                        const items = section.keys
                            .map((key) => byKey.get(key))
                            .filter((i): i is NonNullable<typeof i> =>
                                Boolean(i)
                            );
                        if (items.length === 0) return null;
                        return (
                            <Stack
                                key={section.title}
                                gap={0.5}
                                sx={{ flex: '1 1 220px', minWidth: 220 }}
                            >
                                <Typography
                                    variant="overline"
                                    color="text.secondary"
                                >
                                    {section.title}
                                </Typography>
                                {items.map((item) => (
                                    <Stack
                                        key={item.key}
                                        direction="row"
                                        gap={1}
                                        alignItems="flex-start"
                                    >
                                        {item.filled ? (
                                            <CheckCircle2
                                                size={16}
                                                color="success.main"
                                                style={{ marginTop: 2 }}
                                            />
                                        ) : (
                                            <XCircle
                                                size={16}
                                                color="error.main"
                                                style={{ marginTop: 2 }}
                                            />
                                        )}
                                        <Stack gap={0} minWidth={0}>
                                            <Typography variant="body2">
                                                {item.label}
                                            </Typography>
                                            {item.note ? (
                                                <Typography
                                                    variant="caption"
                                                    color="text.secondary"
                                                >
                                                    {item.note}
                                                </Typography>
                                            ) : null}
                                        </Stack>
                                    </Stack>
                                ))}
                            </Stack>
                        );
                    })}
                </Stack>
                <Stack direction="row" alignItems="center" gap={1}>
                    <ListMusic size={16} />
                    <Typography variant="subtitle2" gutterBottom>
                        Tracks
                    </Typography>
                </Stack>
                <TableContainer>
                    <Table size="small">
                        <TableHead>
                            <TableRow>
                                <TableCell>#</TableCell>
                                <TableCell>Title</TableCell>
                                <TableCell>Artist</TableCell>
                                <TableCell>Length</TableCell>
                                <TableCell>ISRC</TableCell>
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {tracks.map((t) => (
                                <TableRow key={`${t.disc}-${t.track}`}>
                                    <TableCell>
                                        {t.disc > 1 ? `${t.disc}.` : ''}
                                        {t.track}
                                    </TableCell>
                                    <TableCell>{t.title}</TableCell>
                                    <TableCell>{t.artist}</TableCell>
                                    <TableCell>
                                        {trackLengthRep(t.length, false)}
                                    </TableCell>
                                    <TableCell>
                                        <Typography
                                            variant="body2"
                                            color={
                                                t.isrc
                                                    ? undefined
                                                    : 'text.secondary'
                                            }
                                        >
                                            {t.isrc ?? '—'}
                                        </Typography>
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </TableContainer>
            </CardContent>
        </Card>
    );
}

/** Plain text block that can be pasted while filling the release editor */
function formatCopyText(
    prepared: PreparedRelease,
    selectedMbid: Record<string, string> = {},
    media: string = prepared.release.media ?? prepared.default_media_format,
    country: string = prepared.release.country ?? ''
): string {
    const r = prepared.release;
    const lines = [
        `Release: ${r.album}`,
        `Artist: ${r.albumartist}`,
        `Year: ${r.year ?? '?'}`,
        `Format: ${media}`,
        `Label: ${r.label ?? '?'}`,
        `Catalog: ${r.catalognum ?? '?'}`,
        `Barcode: ${r.barcode ?? '?'}`,
        `Country: ${country || r.country || '?'}`,
        `Genre: ${r.genre ?? '?'}`,
        '',
    ];
    if (prepared.artists.length > 0) {
        lines.push('Artists:');
        for (const artist of prepared.artists) {
            const mbid = selectedMbid[artist.name] ?? artist.mbid;
            lines.push(
                `  ${artist.name}` +
                    (mbid ? ` — https://musicbrainz.org/artist/${mbid}` : '')
            );
        }
        lines.push('');
    }
    lines.push('Tracks:');
    for (const t of prepared.tracks) {
        lines.push(
            `  ${t.disc > 1 ? `${t.disc}.` : ''}${t.track}. ${t.title}` +
                ` (${trackLengthRep(t.length, false)})` +
                (t.isrc ? ` [${t.isrc}]` : '')
        );
    }
    lines.push('', `Editor: ${prepared.editor_url}`);
    return lines.join('\n');
}
