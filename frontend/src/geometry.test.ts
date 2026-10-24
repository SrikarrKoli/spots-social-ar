import { describe, expect, it } from "vitest";
import { containedRect, mapFrameBox, mapFramePoint } from "./geometry";

describe("letterboxed camera geometry", () => {
  it("centers a wide frame in a tall container", () => {
    expect(containedRect({ width: 800, height: 800 }, { width: 1600, height: 900 })).toEqual({
      x: 0,
      y: 175,
      width: 800,
      height: 450,
      scale: 0.5,
    });
    expect(mapFramePoint([800, 450], { width: 800, height: 800 }, { width: 1600, height: 900 })).toEqual([400, 400]);
  });

  it("centers a tall frame in a wide container", () => {
    expect(mapFramePoint([500, 500], { width: 1000, height: 500 }, { width: 1000, height: 1000 })).toEqual([500, 250]);
  });

  it("maps an object box through the letterbox transform", () => {
    expect(mapFrameBox([400, 200, 1200, 600], { width: 800, height: 800 }, { width: 1600, height: 900 })).toEqual({
      x: 200,
      y: 275,
      width: 400,
      height: 200,
      scale: 0.5,
    });
  });

  it("returns a safe empty transform for missing dimensions", () => {
    expect(containedRect({ width: 0, height: 500 }, { width: 1000, height: 1000 }).scale).toBe(0);
  });
});
