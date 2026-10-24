import type { Profile } from "../types";

export function Avatar({ profile, small = false }: { profile: Profile; small?: boolean }) {
  return (
    <span
      className={`avatar ${small ? "avatar--small" : ""}`}
      style={{ backgroundColor: profile.color }}
      aria-hidden="true"
    >
      {profile.initials}
    </span>
  );
}
