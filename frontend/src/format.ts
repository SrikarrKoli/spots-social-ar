const NUMBER_WORDS = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"];

export function username(name: string) {
  return name.toLowerCase().replaceAll(" ", ".");
}

export function relativeTime(value: string) {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 60_000));
  if (minutes < 1) return "now";
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.round(hours / 24);
  return days < 7 ? `${days}d` : `${Math.round(days / 7)}w`;
}

export function clockTime(value: string) {
  return new Date(value).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export function dayAndTime(value: string) {
  const date = new Date(value);
  const yesterday = new Date(Date.now() - 86_400_000).toDateString() === date.toDateString();
  if (new Date().toDateString() === date.toDateString()) return clockTime(value);
  if (yesterday) return `Yesterday ${clockTime(value)}`;
  return `${date.toLocaleDateString([], { month: "short", day: "numeric" })}, ${clockTime(value)}`;
}

export function countWord(count: number) {
  return NUMBER_WORDS[count] ?? String(count);
}

export function plural(count: number, noun: string) {
  return `${count} ${count === 1 ? noun : `${noun}s`}`;
}
