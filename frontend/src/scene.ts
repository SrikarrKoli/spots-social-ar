// The calibrated demo scene: a first-person photo of the Zareen's menu with
// each registered menu item anchored to where it is printed in the photo.
export const PLACE_NAME = "Zareen's";
export const PLACE_LOCATION = "Mountain View";
export const DEMO_IMAGE = "/assets/authentic-menu-pov.jpg";
export const DEMO_IMAGE_SIZE = { width: 2268, height: 4032 };
// The photo is shown at DEMO_ZOOM times its fit-to-height size, centred on the mains
// (focus works like CSS object-position, as fractions), so most of the menu stays in view.
export const DEMO_ZOOM = 1.6;
export const DEMO_FOCUS: [number, number] = [0.5, 0.42];

export interface SceneAnchor {
  // Start of the printed dish name's baseline, as fractions of the photo.
  x: number;
  y: number;
  // The printed line's length (fraction of photo width) and slant, for the underline.
  length?: number;
  angle?: number;
  // Where the note sits relative to the anchor, as fractions of photo width/height:
  // the card's bottom-left corner, placed in blank paper.
  callout?: { dx: number; dy: number };
  // Which margin beside the menu the glasses note card opens in (default: left).
  cardSide?: "left" | "right";
}

const anchors: Record<number, SceneAnchor> = {
  7: { x: 0.1, y: 0.6125, length: 0.19, angle: -21, callout: { dx: -0.03, dy: -0.0965 } },
  // Madras Chicken Curry and Beef Chapli Kabab Sizzler, measured from the photo like the one above.
  23: { x: 0.144, y: 0.68 },
  31: { x: 0.621, y: 0.46 },
  // Pani Puri, in the Small Plates column.
  12: { x: 0.48, y: 0.3165, cardSide: "right" },
};

export function anchorFor(markerId: number): SceneAnchor {
  return anchors[markerId] ?? { x: 0.5, y: 0.5 };
}

// The menu item the demo scene highlights first.
export const FEATURED_MARKER = 7;
// Items whose note markers are always visible in the glasses demo (others appear via the arrow keys).
export const PINNED_MARKERS = [7, 12];
