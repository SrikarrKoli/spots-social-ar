import type { Profile } from "./types";

// Illustrative Instagram inbox: friends and strangers who connected through
// notes they left with their glasses. Frontend-only; nothing is stored.

export interface DemoMessage {
  // "me" is whoever is viewing the demo.
  from: string;
  body: string;
  minutesAgo: number;
  sharedNote?: string;
}

export interface DemoConversation {
  id: string;
  title: string;
  people: Profile[];
  subtitle: string;
  unread?: boolean;
  messages: DemoMessage[];
}

const person = (id: string, display_name: string, color: string): Profile => ({
  id,
  display_name,
  initials: display_name.split(" ").map((part) => part[0]).join("").slice(0, 2),
  color,
  photo: `/avatars/${id}.jpg`,
});

const priya = person("priya", "Priya Shah", "#9B5DE5");
const marcus = person("marcus", "Marcus Lee", "#2A9D8F");
const sofia = person("sofia", "Sofia Ramirez", "#F15BB5");
const jordan = person("jordan", "Jordan Kim", "#E9C46A");
const daniel = person("daniel", "Daniel Okafor", "#00BBF9");
const lena = person("lena", "Lena Park", "#F4A261");

export const DEMO_PEOPLE = [priya, marcus, sofia, jordan, daniel, lena];

export const DEMO_STORY_NOTES: Record<string, string> = {
  priya: "Zareen's?",
  marcus: "go medium",
  sofia: "naan heaven",
  jordan: "Hackathon mode",
  daniel: "Who's down for kabab",
  lena: "Spice level: 5",
};

export const DEMO_CONVERSATIONS: DemoConversation[] = [
  {
    id: "dinner-crew",
    title: "Friday dinner",
    people: [priya, jordan, daniel],
    subtitle: "4 members",
    unread: true,
    messages: [
      { from: "priya", body: "ok who picked Zareen's", minutesAgo: 52 },
      { from: "jordan", body: "Vishal did. He has a note on the tikka masala", minutesAgo: 51, sharedNote: "Chicken Tikka Masala" },
      { from: "daniel", body: "garlic naan or regular", minutesAgo: 47 },
            { from: "me", body: "garlic, and get the kabab sizzler for the table", minutesAgo: 38 },
      { from: "jordan", body: "booked 7pm for 4", minutesAgo: 12 },
      { from: "priya", body: "see you there", minutesAgo: 3 },
    ],
  },
  {
    id: "marcus",
    title: marcus.display_name,
    people: [marcus],
    subtitle: "Active 20m ago",
    unread: true,
    messages: [
      { from: "marcus", body: "is the madras curry actually that spicy", minutesAgo: 130 },
      { from: "me", body: "yeah, ask for medium", minutesAgo: 124 },
      { from: "marcus", body: "medium was perfect, thanks", minutesAgo: 30 },
      { from: "marcus", body: "replied on your note", minutesAgo: 29, sharedNote: "Madras Chicken Curry" },
    ],
  },
  {
    id: "hack-team",
    title: "Lena, Daniel, Sofia",
    people: [lena, daniel, sofia],
    subtitle: "4 members",
    messages: [
      { from: "lena", body: "can someone grab the projector adapter", minutesAgo: 300 },
      { from: "sofia", body: "on it", minutesAgo: 290 },
      { from: "me", body: "pushed the latest build", minutesAgo: 75 },
      { from: "daniel", body: "run-through at 3?", minutesAgo: 70 },
    ],
  },
  {
    id: "sofia",
    title: sofia.display_name,
    people: [sofia],
    subtitle: "Active 5m ago",
    messages: [
      { from: "sofia", body: "where was that kabab place", minutesAgo: 240 },
      { from: "me", body: "Zareen's in Mountain View", minutesAgo: 236 },
      { from: "sofia", body: "going saturday", minutesAgo: 60 },
    ],
  },
  {
    id: "priya",
    title: priya.display_name,
    people: [priya],
    subtitle: "Active now",
    messages: [
      { from: "me", body: "Did you try the garlic naan?", minutesAgo: 400 },
      { from: "priya", body: "yes, so good", minutesAgo: 395 },
          ],
  },
  {
    id: "jordan",
    title: jordan.display_name,
    people: [jordan],
    subtitle: "Active 1h ago",
    messages: [
      { from: "jordan", body: "you driving friday?", minutesAgo: 11 },
    ],
  },
];

// Activity Spots posts around the shared note, so the thread reads like a real timeline.
export interface SpotsUpdate {
  minutesAgo: number;
  body: string;
  person?: Profile;
  quote?: string;
}

export const DEMO_SPOTS_BEFORE: SpotsUpdate[] = [
  { minutesAgo: 4320, body: "Welcome to Spots. Notes you leave with your glasses land here, along with replies from friends." },
  { minutesAgo: 2890, person: marcus, body: "Marcus replied to your note on the Madras Chicken Curry", quote: "medium was perfect, thanks" },
  { minutesAgo: 2210, person: sofia, body: "Sofia saved your note on the Beef Chapli Kabab" },
];

export const DEMO_SPOTS_AFTER: SpotsUpdate[] = [
  { minutesAgo: 260, person: priya, body: "Priya is at Zareen's and saw your note" },
  { minutesAgo: 95, person: jordan, body: "Jordan replied to your note", quote: "adding garlic naan to the order" },
];

// A friend chat for real people who haven't traded notes yet.
export const DEMO_FRIEND_MESSAGES: DemoMessage[] = [
  { from: "them", body: "you still at zareen's?", minutesAgo: 905 },
  { from: "me", body: "just left. put a note on the tikka masala", minutesAgo: 900 },
  { from: "them", body: "it popped up in Spots", minutesAgo: 880, sharedNote: "Chicken Tikka Masala" },
  { from: "them", body: "garlic naan noted", minutesAgo: 879 },
  { from: "me", body: "trust me on that one", minutesAgo: 870 },
];
