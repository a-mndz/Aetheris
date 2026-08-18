export function randId() { return Math.random().toString(36).slice(2, 10); }

export function picsum(seed, w = 1600, h = 1000) { return `https://picsum.photos/seed/${seed}/${w}/${h}`; }
