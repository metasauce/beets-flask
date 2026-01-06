import { Home, Inbox, Library, Search, Terminal } from 'lucide-react';
import { MouseEvent, ReactElement, useRef } from 'react';
import { Box, BoxProps, darken, Typography, useTheme } from '@mui/material';
import { styled } from '@mui/material/styles';
import Tab, { tabClasses, TabProps } from '@mui/material/Tab';
import Tabs, { tabsClasses } from '@mui/material/Tabs';
import { createLink, LinkProps, useRouterState } from '@tanstack/react-router';
import { useConfig } from '@/api/config.ts';

export const NAVBAR_HEIGHT = {
    desktop: '48px',
    mobile: '74px',
};

const StyledTabs = styled(Tabs)(({ theme }) => ({
    color: 'inherit',
    overflow: 'hidden',
    display: 'flex',
    width: '100%',
    justifyContent: 'center',
    [`& .${tabsClasses.indicator}`]: {
        position: 'absolute',
        top: `calc(50% - 8px)`,
        height: '16px',
        filter: 'blur(50px)',
        backgroundColor: theme.palette.secondary.main,
        zIndex: -1,
    },
    [`& .MuiTabs-scroller`]: {
        width: '100%',
        overflow: 'visible',
    },
    // Spacing of tabs for different breakpoints
    [`& .MuiTabs-flexContainer`]: {
        width: '100%',
        gap: '4px',
        justifyContent: 'center',
        [theme.breakpoints.up('laptop')]: {
            gap: '30px',
        },
    },
    [`&:hover .mouse-trail`]: {
        opacity: 1,
    },

    // Mobile grid for equal spacing
    [theme.breakpoints.down('laptop')]: {
        '& .MuiTabs-list': {
            width: 'auto',
            display: 'grid',
            gridTemplateColumns: 'repeat(5, 1fr)',
            gridTemplateRows: '1fr',
            alignItems: 'center',
            justifyItems: 'center',
        },
        '& .MuiTabs-scroller': {
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
        },
        background: 'linear-gradient(to bottom, transparent, black)',
    },
}));

interface StyledTabProps
    extends Omit<LinkProps, 'children'>, Omit<TabProps, 'ref'> {
    label: string | ReactElement;
}

const StyledTab = styled(createLink(Tab))<StyledTabProps>(({ theme }) => ({
    lineHeight: 'inherit',
    marginTop: 7,
    minHeight: 32,
    minWidth: 0,
    flexDirection: 'row',
    letterSpacing: '1px',
    justifyContent: 'center',
    gap: '0.5rem',
    textTransform: 'uppercase',
    overflow: 'visible',
    transition: 'color 0.3s linear',
    '& svg': {
        fontSize: 16,
        width: 16,
        height: 16,
    },
    [theme.breakpoints.up(960)]: {
        minWidth: 0,
    },
    [`& .${tabClasses.labelIcon}`]: {
        minHeight: 53,
    },
    [`& .${tabClasses.icon}`]: {
        marginBottom: 0,
    },
    [`&:hover`]: {
        color: darken(theme.palette.secondary.main, 0.2),
        transition: 'color 1s linear, text-shadow 5s ease-in',
        textShadow: `0 0 50px ${theme.palette.secondary.main}`,
    },
    [`&[data-status="active"]`]: {
        color: theme.palette.secondary.main,
    },

    //Mobile styles
    [theme.breakpoints.down('laptop')]: {
        marginTop: 0,
        height: NAVBAR_HEIGHT.mobile,
        display: 'flex',
        zIndex: 1,
        flexDirection: 'column',

        '& svg': {
            fontSize: 16,
            width: theme.iconSize.lg,
            height: theme.iconSize.lg,
        },
    },
}));

const TabLabel = styled(Typography)(({ theme }) => ({
    marginLeft: 8,
    lineHeight: '12px',
    [theme.breakpoints.down('laptop')]: {
        marginLeft: 0,
        fontSize: theme.typography.caption.fontSize,
        lineHeight: 'inherit',
        textAlign: 'center',
        width: '100%',
    },
}));

function NavItem({ label, ...props }: StyledTabProps) {
    return (
        // @ts-expect-error: WTF is happening here. MUI-Update broke typing!
        <StyledTab
            label={<TabLabel>{label}</TabLabel>}
            disableRipple
            {...props}
        />
    );
}

function NavTabs() {
    const theme = useTheme();
    const config = useConfig();

    const location = useRouterState({ select: (s) => s.location });
    let basePath = location.pathname.split('/')[1];

    // only needed temporarily until search gets an icon in the toolbar!
    if (basePath === 'library') {
        basePath += '/' + location.pathname.split('/')[2];
    }

    const navItems: StyledTabProps[] = [
        { label: 'Home', icon: <Home />, to: '/' },
        { label: 'Inbox', icon: <Inbox />, to: '/inbox' },
        //{ label: "Session", icon: <Inbox />, to: '/sessiondraft'},
        { label: 'Library', icon: <Library />, to: '/library/browse' },
        { label: 'Search', icon: <Search />, to: '/library/search' },
    ];

    if (config.gui.terminal.enable) {
        navItems.push({
            label: '',
            icon: <Terminal stroke={theme.palette.primary.main} />,
            to: '/terminal',
        });
    }

    const currentIdx = navItems.findIndex((item) => item.to === '/' + basePath);
    const ref = useRef<HTMLDivElement>(null);

    const handleMouseMove = (e: MouseEvent) => {
        ref.current?.style.setProperty('--mouse-x', `${e.clientX}px`);
        ref.current?.style.setProperty('--mouse-y', `${e.clientY}px`);
    };

    return (
        <StyledTabs
            ref={ref}
            value={currentIdx === -1 ? false : currentIdx}
            onMouseMove={handleMouseMove}
        >
            {navItems.map((item) => (
                <NavItem key={item.to} {...item} />
            ))}
            {/* Mouse hover effect */}
            <MouseTrail />
        </StyledTabs>
    );
}

/** Navbar component
 *
 * on desktop: fixed to the top
 * on mobile: fixed to the bottom
 */
export default function NavBar(props: BoxProps) {
    return (
        <Box
            sx={(theme) => ({
                position: 'fixed',
                bottom: 0,
                zIndex: 2,
                width: '100dvw',
                height: NAVBAR_HEIGHT.mobile,
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'flex-start',
                backdropFilter: 'blur(25px)',
                //backgroundColor: "#21252933",

                [theme.breakpoints.up('laptop')]: {
                    top: 0,
                    borderBottom: '1px solid',
                    borderColor: 'divider',
                    height: NAVBAR_HEIGHT.desktop,
                },
            })}
            {...props}
        >
            <NavTabs />
        </Box>
    );
}

// Weird workaround for mui problems in console as it parses props to its children
const MouseTrail = () => {
    return (
        <Box
            className="mouse-trail"
            sx={(theme) => ({
                top: 'var(--mouse-y)',
                left: 'var(--mouse-x)',
                width: '10px',
                height: '10px',
                backgroundColor: theme.palette.secondary.main,
                filter: 'blur(25px)',
                pointerEvents: 'none',
                transition: 'opacity 0.3s ease-in-out',
                transform: 'translate(-50%, -50%)',
                position: 'absolute',
                opacity: 0,
                zIndex: -1,
            })}
        />
    );
};
