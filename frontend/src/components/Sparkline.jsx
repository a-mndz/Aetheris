export default function Sparkline({ data: sparklineValues }) {
  const w = 148, h = 36;
  const max = Math.max(...sparklineValues, 1), min = Math.min(...sparklineValues, 0);
  const range = max - min || 1;
  const points = sparklineValues.map((v, i) => {
    const x = (i / (sparklineValues.length - 1)) * w;
    const y = h - ((v - min) / range) * h;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      <polyline points={points} fill="none" stroke="var(--c-green)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
