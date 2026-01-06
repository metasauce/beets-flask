import React, {
    createContext,
    Dispatch,
    HtmlHTMLAttributes,
    SetStateAction,
    useCallback,
    useEffect,
    useRef,
    useState,
} from 'react';
import { FitAddon as xTermFitAddon } from '@xterm/addon-fit';
import { Terminal as xTerminal } from '@xterm/xterm';

import useSocket from '@/components/common/websocket/useSocket';

import 'node_modules/@xterm/xterm/css/xterm.css';
import { useConfig } from '@/api/config.ts';
import { Socket } from 'socket.io-client';

// match our style - this is somewhat redundant with main.css
const xTermTheme = {
    red: '#C0626B',
    green: '#A4BF8C',
    yellow: '#EBCB8C',
    blue: '#7EA2BF',
    magenta: '#B48EAD',
    cyan: '#8FBCBB',
    brightBlack: '#818689',
    brightRed: '#D0737F',
    brightGreen: '#B5D0A0',
    brightYellow: '#F0D9A6',
    brightBlue: '#8FB8D1',
    brightMagenta: '#C79EC4',
    brightCyan: '#A3CDCD',
};

export function Terminal(props: HtmlHTMLAttributes<HTMLDivElement>) {
    const ref = useRef<HTMLDivElement>(null);
    const { term, resetTerm, socket } = useTerminalContext();

    // we have to recreate the terminal on every mount of the component.
    // not sure why we cannot restore.
    useEffect(resetTerm, [resetTerm]);

    // PS 2025-04-13: Wanted to use this to only query the history when scrolling
    // but its super laggy and the scroll pos makes no sense. might be that we
    // do not use the xterm js buildin scrolling, and scroll an outside div instead?
    // useEffect(() => {
    //     if (!term || !socket) return;

    //     const handleScroll = (scrollPos: number) => {
    //         console.log("Scroll event", scrollPos);
    //         if (scrollPos > 0) {
    //             socket.emit("ptyScroll", { scrollPos });
    //         }
    //     };

    //     const scrollHandler = term.onScroll(handleScroll);
    //     return () => {
    //         scrollHandler.dispose();
    //     };
    // }, [term, socket]);

    // resetting term also retriggers this guy.
    // having socket as a dependencies should make sure we retrigger when
    // the if socket had connection issues.
    useEffect(() => {
        if (!ref.current || !term || !socket) return;
        const ele = ref.current;
        function copyPasteHandler(e: KeyboardEvent) {
            if (!term) return false;

            if (e.type !== 'keydown') return true;

            if (e.ctrlKey && e.shiftKey) {
                const key = e.key.toLowerCase();
                if (key === 'v') {
                    // ctrl+shift+v: paste whatever is in the clipboard
                    navigator.clipboard
                        .readText()
                        .then((toPaste) => {
                            term.write(toPaste);
                        })
                        .catch(console.error);
                    return false;
                } else if (key === 'c' || key === 'x') {
                    // ctrl+shift+x: copy whatever is highlighted to clipboard

                    // 'x' is used as an alternate to 'c' because ctrl+c is taken
                    // by the terminal (SIGINT) and ctrl+shift+c is taken by the browser
                    // (open devtools).
                    // I'm not aware of ctrl+shift+x being used by anything in the terminal
                    // or browser
                    const toCopy = term.getSelection();
                    navigator.clipboard.writeText(toCopy).catch(console.error);
                    term.focus();
                    return false;
                }
            }
            return true;
        }

        term.attachCustomKeyEventHandler(copyPasteHandler);

        const fitAddon = new xTermFitAddon();
        term.loadAddon(fitAddon);
        term.open(ele);
        term.focus();
        fitAddon.fit();

        const resizeObserver = new ResizeObserver(() => {
            fitAddon.fit();
        });
        resizeObserver.observe(ele);

        return () => {
            term.dispose();
            if (ele) resizeObserver.unobserve(ele);
        };
    }, [term, ref, socket]);

    return <div ref={ref} {...props} />;
}

export interface TerminalContextI {
    open: boolean;
    toggle: () => void;
    setOpen: Dispatch<SetStateAction<boolean>>;
    inputText: (input: string) => void;
    clearInput: () => void;
    resetTerm: () => void;
    socket: Socket | null;
    term?: xTerminal;
}

const TerminalContext = createContext<TerminalContextI | null>(null);

export function TerminalContextProvider({
    children,
}: {
    children: React.ReactNode;
}) {
    const config = useConfig();

    if (!config.gui.terminal.enable) {
        const noop = () => {};

        return (
            <TerminalContext.Provider
                value={{
                    open: false,
                    toggle: noop,
                    resetTerm: noop,
                    setOpen: noop,
                    inputText: noop,
                    clearInput: noop,
                    socket: null,
                }}
            >
                {children}
            </TerminalContext.Provider>
        );
    }

    return <InitTerminalContext>{children}</InitTerminalContext>;
}

function InitTerminalContext({ children }: { children: React.ReactNode }) {
    const { socket, isConnected } = useSocket('terminal');
    const [open, setOpen] = useState(false);
    const [term, setTerm] = useState<xTerminal>();

    const resetTerm = useCallback(() => {
        /** Creates a new terminal and disposes the old one
         */
        setTerm((old) => {
            if (old) old.dispose();
            const t2 = new xTerminal({
                theme: xTermTheme,
                cursorBlink: true,
                macOptionIsMeta: true,
                allowTransparency: true,
                scrollback: 500,
            });
            t2.write('Connecting...');
            return t2;
        });
    }, []);

    // useEffect(resetTerm, [resetTerm]);

    const onCursorUpdate = useCallback(
        (data: { x: number; y: number }) => {
            if (!term) return;
            // xterm uses 1-based indexing
            // console.log("Cursor update", data);
            term.write(`\x1b[${data.y + 1};${data.x + 1}H`);
        },
        [term]
    );

    const onOutput = useCallback(
        (data: {
            output: string[];
            x: number;
            y: number;
            history: string[];
        }) => {
            if (!term) return;
            // neither clear nor reset seem to do the full job.
            // term.clear();
            // term.reset();
            term.write('\x1Bc'); // ANSI escape sequence to clear the screen

            if (data.history.length > 0) {
                term.write(data.history.join('\r\n') + '\r\n');
            }

            // Note: tmux does not remove trailing whitespaces when backspacing.
            // Therefore we also send the tmux cursor position along with the output
            // to move the frontend cursor using escape sequences
            // Write current output
            term.write(data.output.join('\r\n'));

            // if we want history to stay offscreen
            const remainingRows = Math.max(0, term.rows - data.output.length);
            if (remainingRows > 0) {
                term.write('\r\n'.repeat(remainingRows));
            }

            // Position cursor
            term.write(`\x1b[${data.y + 1};${data.x + 1}H`);
        },
        [term]
    );

    // Attach socket handler
    useEffect(() => {
        if (!term || !isConnected || !socket) return;

        // spaces are needed to clear out the longer "Connecting..."
        term.writeln('\rConnected!   ');

        const onInput = term.onData((data) => {
            if (data === '\x01' || data === '\x04') {
                // prevent ctrl+a because it can detach tmux, and ctrl+d because it can close the terminal
                return;
            }
            socket.emit('ptyInput', { input: data });
        });

        const onResize = term.onResize(({ cols, rows }) => {
            console.log(
                `Terminal was resized to ${cols} cols and ${rows} rows.`
            );
            socket.emit('ptyResize', { cols, rows: rows });
        });

        socket.on('ptyOutput', onOutput);
        socket.on('ptyCursorPosition', onCursorUpdate);

        // resize once on connect (after we fitted size on mount)
        socket.emit('ptyResize', { cols: term.cols, rows: term.rows });
        // request server update, so show whats actually on the pty when connecting
        socket.emit('ptyResendOutput');

        return () => {
            onResize.dispose();
            onInput.dispose();
            socket.off('ptyOutput', onOutput);
            socket.off('ptyCursorPosition', onCursorUpdate);
        };
    }, [isConnected, term, socket, onOutput, onCursorUpdate]);

    // make first responder directly after opening
    useEffect(() => {
        if (open && term) {
            term.focus();
        }
    }, [open, term]);

    function inputText(t: string) {
        if (!socket) {
            console.error('No socket available');
            return;
        }
        socket.emit('ptyInput', { input: t });
    }

    function clearInput() {
        if (!socket) {
            console.error('No socket available');
            return;
        }
        socket.emit('ptyInput', { input: '\x15' });
    }

    const terminalState: TerminalContextI = {
        open,
        toggle: () => setOpen(!open),
        resetTerm,
        setOpen,
        inputText,
        clearInput,
        socket,
        term,
    };

    return (
        <TerminalContext.Provider value={terminalState}>
            {children}
        </TerminalContext.Provider>
    );
}

export function useTerminalContext() {
    const context = React.useContext(TerminalContext);

    if (!context) {
        throw new Error(
            'useTerminalContext must be used within a TerminalContextProvider'
        );
    }
    return context;
}
