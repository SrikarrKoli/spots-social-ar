import type { Profile } from "../types";

type AvatarSize = "xs" | "sm" | "md" | "lg" | "xl";

// Without a photo, Instagram shows its default portrait; the glasses UI shows initials instead.
export function Avatar({
  profile,
  size = "md",
  small = false,
  ring = false,
  fallback = "portrait",
}: {
  profile: Profile;
  size?: AvatarSize;
  small?: boolean;
  ring?: boolean;
  fallback?: "portrait" | "initials";
}) {
  return (
    <span
      className={`avatar avatar--${small ? "sm" : size} ${ring ? "avatar--ring" : ""} ${!profile.photo && fallback === "initials" ? "avatar--initials" : ""}`}
      aria-hidden="true"
    >
      {profile.photo ? <img src={profile.photo} alt="" /> : fallback === "initials" ? profile.initials : <DefaultPortrait />}
    </span>
  );
}

export function SpotsAvatar({ size = "md" }: { size?: AvatarSize }) {
  return (
    <span className={`avatar avatar--${size} avatar--spots`} aria-hidden="true">
      <PinMark />
    </span>
  );
}

// Instagram's default portrait for people without a photo.
function DefaultPortrait() {
  return (
    <svg viewBox="0 0 40 40" aria-hidden="true">
      <circle cx="20" cy="15.5" r="7" fill="#8e8e8e" />
      <path d="M6.5 36c1.6-7.2 7-11 13.5-11s11.9 3.8 13.5 11z" fill="#8e8e8e" />
    </svg>
  );
}

// Spots's mark: a note with a pin at its foot.
export function PinMark({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 4.5h14a1.5 1.5 0 0 1 1.5 1.5v9a1.5 1.5 0 0 1-1.5 1.5h-5.2L12 19.6l-1.8-3.1H5A1.5 1.5 0 0 1 3.5 15V6A1.5 1.5 0 0 1 5 4.5z" fill="currentColor" />
      <path d="M7.5 9h9M7.5 12h6" stroke="var(--pin)" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
