import { Bug as BugOn, BugOff } from 'lucide-react';
import { useState } from 'react';
import { ReactNode, useMemo } from 'react';
import { Box } from '@mui/material';
import IconButton from '@mui/material/IconButton';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableRow from '@mui/material/TableRow';
import Tooltip from '@mui/material/Tooltip';
import { useSuspenseQuery } from '@tanstack/react-query';

import { Album as AlbumT, albumQueryOptions } from '@/api/library';

import { CoverArt } from './coverArt';

export function AlbumById({ albumId }: { albumId: number }) {
    const { data: item } = useSuspenseQuery(
        albumQueryOptions(albumId, false, false) // minimal
    );

    return <Album album={item} />;
}

// for now this is the same as ItemView.
export function Album({ album }: { album: AlbumT<false, false> }) {
    const [detailed, setDetailed] = useState(false);

    return (
        <>
            <Box
                sx={{
                    display: 'flex',
                    flexDirection: 'column',
                    flexGrow: 1,
                    alignItems: 'center',
                    justifyContent: 'flex-start',
                    overflow: 'auto',
                }}
            >
                <CoverArt
                    type="album"
                    beetsId={album.id}
                    sx={{
                        width: '200px',
                        height: '200px',
                        aspectRatio: '1 / 1',
                        objectFit: 'cover',
                        borderRadius: 0,
                    }}
                />
                <Tooltip title="Toggle Details" className="ml-auto mt-1">
                    <IconButton
                        color="primary"
                        onClick={() => setDetailed(!detailed)}
                    >
                        {detailed && <BugOff size="1em" />}
                        {!detailed && <BugOn size="1em" />}
                    </IconButton>
                </Tooltip>
                <DetailsTable obj={album} keys={detailed ? 'all' : 'basic'} />
            </Box>
        </>
    );
}

const basicAlbumKeys = [
    'album',
    'albumartist',
    'albumtype',
    'genre',
    'comp',
    'label',
    'year',
    'added',
];

/** FIXME: This needs a rewrite badly! */
export function DetailsTable({
    obj,
    keys,
}: {
    obj: AlbumT<false, false>;
    keys?: string | string[];
}) {
    if (!keys || keys === 'basic') {
        keys = basicAlbumKeys;
    } else if (keys === 'all') {
        keys = Object.keys(obj);
        // we only added name for backend-frontend consistency, its not a beets-field
        // note: this could cause problems if a user adds a custom field "name"
        keys = keys.filter((key) => key !== 'name');
    }

    const keys_list: string[] = keys as string[];

    const maxKeyWidth = useMemo(() => {
        const keyWidths = keys_list.map((key) => key.length);
        return Math.max(...keyWidths) * 10;
    }, [keys_list]);

    return (
        <TableContainer>
            <Table size="small">
                <TableBody>
                    {keys_list.map((key, i) => {
                        return (
                            <TableRow
                                key={i}
                                sx={{
                                    '&:last-child td, &:last-child th': {
                                        border: 0,
                                    },
                                    'td, th': {
                                        borderBottom: '0.5px solid #495057',
                                    },
                                }}
                            >
                                <TableCell
                                    align="right"
                                    sx={{
                                        width: maxKeyWidth,
                                    }}
                                >
                                    {key}
                                </TableCell>
                                <TableCell align="left">
                                    {parse(key, obj[key])}
                                </TableCell>
                            </TableRow>
                        );
                    })}
                </TableBody>
            </Table>
        </TableContainer>
    );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function parse(key: string, value: any): ReactNode {
    // format n/a
    if (value === null || value === undefined || value === '') {
        return <span style={{ opacity: 0.3 }}>n/a</span>;
    }
    if (key === 'length') {
        // format to 2h 30:12
        const hours = Math.floor(value / 3600);
        const minutes = Math.floor((value % 3600) / 60);
        const seconds = Math.floor(value % 60);
        return `${hours ? `${hours}h ` : ''}${minutes}:${seconds.toString().padStart(2, '0')}`;
    }
    if (key === 'size') {
        // format to 2.3 MB
        const size = value / 1024 / 1024;
        return `${size.toFixed(1)} MB`;
    }
    if (key === 'samplerate') {
        // format to 44.1 kHz
        return `${value / 1000} kHz`;
    }
    if (key === 'bitrate') {
        // format to 320 kbps, no past decimal
        return `${Math.round(value / 1000)} kbps`;
    }
    if (['mtime', 'added'].includes(key)) {
        // format to 2023-07-14 12:34:56
        return new Date(value * 1000).toLocaleString();
    }
    if (key === 'comp') {
        // format to Yes/No
        return value ? 'Yes' : 'No';
    }
    if (key === 'bpm' && value === 0) {
        // format to n/a
        return <span style={{ opacity: 0.3 }}>n/a</span>;
    }
    return String(value);
}
