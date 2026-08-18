export function truncate(s, n = 56) { return s.length > n ? s.slice(0, n) + "\u2026" : s; }

export function getScoreTone(score) {
  if (score >= 90) return "high";
  if (score >= 70) return "mid";
  return "low";
}
