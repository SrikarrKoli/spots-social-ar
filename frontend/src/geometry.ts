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

export function mapFrameBox(
  box: [number, number, number, number],
  container: Size,
  frame: Size,
): ContainedRect {
  const rect = containedRect(container, frame);
  return {
    x: rect.x + box[0] * rect.scale,
    y: rect.y + box[1] * rect.scale,
    width: (box[2] - box[0]) * rect.scale,
    height: (box[3] - box[1]) * rect.scale,
    scale: rect.scale,
  };
}

// Like CSS object-fit: cover with object-position at `focus` (fractions of the overflow).
export function coverRect(container: Size, media: Size, focus: [number, number] = [0.5, 0.5]): ContainedRect {
  if (container.width <= 0 || container.height <= 0 || media.width <= 0 || media.height <= 0) {
    return { x: 0, y: 0, width: 0, height: 0, scale: 0 };
  }
  const scale = Math.max(container.width / media.width, container.height / media.height);
  const width = media.width * scale;
  const height = media.height * scale;
  return {
    x: (container.width - width) * focus[0],
    y: (container.height - height) * focus[1],
    width,
    height,
    scale,
  };
}

// Scales media to `zoom` times its fit-inside size (never beyond cover), placed like object-position at `focus`.
export function zoomedRect(container: Size, media: Size, zoom: number, focus: [number, number] = [0.5, 0.5]): ContainedRect {
  if (container.width <= 0 || container.height <= 0 || media.width <= 0 || media.height <= 0) {
    return { x: 0, y: 0, width: 0, height: 0, scale: 0 };
  }
  const fit = Math.min(container.width / media.width, container.height / media.height);
  const cover = Math.max(container.width / media.width, container.height / media.height);
  const scale = Math.min(fit * zoom, cover);
  const width = media.width * scale;
  const height = media.height * scale;
  return {
    x: (container.width - width) * focus[0],
    y: (container.height - height) * focus[1],
    width,
    height,
    scale,
  };
}
