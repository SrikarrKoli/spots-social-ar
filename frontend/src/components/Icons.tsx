import type { ReactNode, SVGProps } from "react";

export type IconName =
  | "instagram"
  | "home"
  | "reels"
  | "messages"
  | "search"
  | "explore"
  | "heart"
  | "create"
  | "glasses"
  | "menu"
  | "threads"
  | "comment"
  | "share"
  | "bookmark"
  | "more"
  | "camera"
  | "back"
  | "chevronDown"
  | "chevronRight"
  | "compose"
  | "phone"
  | "video"
  | "info"
  | "bell"
  | "pin"
  | "clock"
  | "notes"
  | "mic"
  | "image"
  | "sticker"
  | "smile"
  | "close"
  | "external"
  | "expand"
  | "settings"
  | "speaker"
  | "dish"
  | "apps";

interface IconProps extends SVGProps<SVGSVGElement> {
  name: IconName;
  filled?: boolean;
}

export function Icon({ name, filled = false, ...props }: IconProps) {
  const common = {
    fill: filled ? "currentColor" : "none",
    stroke: "currentColor",
    strokeWidth: 1.9,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };

  const paths: Record<IconName, ReactNode> = {
    instagram: <><rect x="3" y="3" width="18" height="18" rx="5" /><circle cx="12" cy="12" r="4.25" /><circle cx="17.4" cy="6.7" r=".8" fill="currentColor" stroke="none" /></>,
    home: <><path d="M3 10.5 12 3l9 7.5v9a1.5 1.5 0 0 1-1.5 1.5h-5v-6h-5v6h-5A1.5 1.5 0 0 1 3 19.5z" /></>,
    reels: <><rect x="3" y="3.5" width="18" height="17" rx="4" /><path d="m3.5 8 17-3M8 4l3 4m3.5-5 3 4M9.5 12.2l5.8 3.3-5.8 3.3z" /></>,
    messages: <><path d="M21 11.6a8.7 8.7 0 0 1-9.2 8.7 9.7 9.7 0 0 1-3.7-.9L3 21l1.7-4.8a8.3 8.3 0 0 1-1.3-4.6 8.8 8.8 0 0 1 17.6 0Z" /><path d="m7.5 13.6 3-3.2 2.4 2 3.6-3.6-3 3.2-2.4-2z" /></>,
    search: <><circle cx="10.6" cy="10.6" r="7.1" /><path d="m16 16 5 5" /></>,
    explore: <><circle cx="12" cy="12" r="9" /><path d="m15.7 8.3-2.1 5.3-5.3 2.1 2.1-5.3z" /></>,
    heart: <path d="M20.8 8.3c0 5-8.8 11-8.8 11s-8.8-6-8.8-11A4.8 4.8 0 0 1 12 5.6a4.8 4.8 0 0 1 8.8 2.7Z" />,
    create: <><rect x="3" y="3" width="18" height="18" rx="5" /><path d="M12 8v8M8 12h8" /></>,
    glasses: <><rect x="2" y="8" width="8.5" height="7.5" rx="3.5" /><rect x="13.5" y="8" width="8.5" height="7.5" rx="3.5" /><path d="M10.5 11c1-.8 2-.8 3 0" /></>,
    menu: <><path d="M4 7h16M4 12h16M4 17h16" /></>,
    threads: <path d="M18.8 8.4c-.7-3.2-3.1-5-6.7-5-5 0-8.1 3.6-8.1 8.7 0 5.2 3 8.5 8.1 8.5 4.5 0 7.7-2.4 7.7-5.9 0-3.2-2.6-5.4-6.4-5.4-3 0-5.1 1.6-5.1 3.9 0 2 1.6 3.4 3.9 3.4 2.8 0 4.6-1.8 4.6-4.8 0-1.3-.2-2.4-.6-3.4" />,
    comment: <path d="M21 11.7a8.8 8.8 0 0 1-9.1 8.7 9.5 9.5 0 0 1-4-.9L3 21l1.6-4.7A8.7 8.7 0 1 1 21 11.7Z" />,
    share: <path d="m22 2-9.6 19-2.1-8.3L2 9.5 22 2Zm-11.7 10.7L22 2" />,
    bookmark: <path d="M5 3.5h14v17L12 16l-7 4.5z" />,
    more: <><circle cx="5" cy="12" r="1" fill="currentColor" stroke="none" /><circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" /><circle cx="19" cy="12" r="1" fill="currentColor" stroke="none" /></>,
    camera: <><path d="M4 8.5h3l1.5-2h7l1.5 2h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1Z" /><circle cx="12" cy="14" r="3.5" /></>,
    back: <path d="m15.5 4-8 8 8 8" />,
    chevronDown: <path d="m6 9 6 6 6-6" />,
    chevronRight: <path d="m9 6 6 6-6 6" />,
    compose: <><path d="M12 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-6" /><path d="M18.4 2.6a2 2 0 0 1 2.9 2.9L12 14.8l-3.8.9.9-3.8z" /></>,
    phone: <path d="M21 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 1.1 4.2 2 2 0 0 1 3.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L7 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2Z" />,
    video: <><rect x="2" y="6" width="14" height="12" rx="2.5" /><path d="m16 10.5 6-3.5v10l-6-3.5" /></>,
    info: <><circle cx="12" cy="12" r="9.5" /><path d="M12 11v6" /><circle cx="12" cy="7.6" r=".6" fill="currentColor" /></>,
    bell: <><path d="M18 8.5a6 6 0 0 0-12 0c0 6.5-3 8.5-3 8.5h18s-3-2-3-8.5" /><path d="M13.7 20.5a2 2 0 0 1-3.4 0" /></>,
    pin: <><path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 0 1 16 0Z" /><circle cx="12" cy="10" r="3" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    notes: <><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.4-4.6A8 8 0 1 1 21 12Z" /><path d="M8.5 10.5h7M8.5 13.5h4.5" /></>,
    mic: <><rect x="9" y="2.5" width="6" height="12" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3.5" /></>,
    image: <><rect x="3" y="3" width="18" height="18" rx="4" /><circle cx="9" cy="9" r="1.8" /><path d="m21 15-4.5-4.5L6 21" /></>,
    sticker: <><path d="M21 12.5V7a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v10a4 4 0 0 0 4 4h5.5" /><path d="M21 12.5 12.5 21c0-4.7 3.8-8.5 8.5-8.5Z" /><path d="M8.5 13.5c1 1.3 2.6 1.8 4 1.4" /><circle cx="9" cy="9" r=".6" fill="currentColor" /><circle cx="15" cy="9" r=".6" fill="currentColor" /></>,
    smile: <><circle cx="12" cy="12" r="9.5" /><path d="M8 14.5s1.5 2 4 2 4-2 4-2" /><circle cx="9" cy="9.5" r=".7" fill="currentColor" /><circle cx="15" cy="9.5" r=".7" fill="currentColor" /></>,
    close: <path d="M6 6l12 12M18 6 6 18" />,
    external: <><path d="M14 3h7v7M10 14 21 3" /><path d="M19 14v4a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3V8a3 3 0 0 1 3-3h4" /></>,
    expand: <path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7" />,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5v.2a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1h-.2a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5v-.2a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1h.2a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z" /></>,
    speaker: <><path d="M11 5 6 9H2v6h4l5 4z" /><path d="M15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14" /></>,
    dish: <><path d="M3 15h18" /><path d="M4.5 15a7.5 7.5 0 0 1 15 0" /><path d="M12 7.5V6M2 18h20" /></>,
    apps: <><rect x="3" y="3" width="7" height="7" rx="2" /><rect x="14" y="3" width="7" height="7" rx="2" transform="rotate(45 17.5 6.5)" /><rect x="3" y="14" width="7" height="7" rx="2" /><rect x="14" y="14" width="7" height="7" rx="2" /></>,
  };

  return <svg viewBox="0 0 24 24" aria-hidden="true" {...common} {...props}>{paths[name]}</svg>;
}
