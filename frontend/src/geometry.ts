export interface Size {
  width: number;
  height: number;
}

export interface ContainedRect extends Size {
  x: number;
  y: number;
  scale: number;
}

export function containedRect(container: Size, media: Size): ContainedRect {
  if (
    container.width <= 0 ||
    container.height <= 0 ||
    media.width <= 0 ||
    media.height <= 0
  ) {
    return { x: 0, y: 0, width: 0, height: 0, scale: 0 };
  }
  const scale = Math.min(
    container.width / media.width,
    container.height / media.height,
  );
  const width = media.width * scale;
  const height = media.height * scale;
  return {
    x: (container.width - width) / 2,
    y: (container.height - height) / 2,
    width,
    height,
    scale,
  };
}

export function mapFramePoint(
  point: [number, number],
  container: Size,
  frame: Size,
): [number, number] {
  const rect = containedRect(container, frame);
  return [rect.x + point[0] * rect.scale, rect.y + point[1] * rect.scale];
}
