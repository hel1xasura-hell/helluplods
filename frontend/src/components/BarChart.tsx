import type { SeriesPoint } from "../types/api";

/** Small accessible SVG bar chart (no chart library needed). */
export function BarChart({ data, label }: { data: SeriesPoint[]; label: string }) {
  const max = Math.max(1, ...data.map((d) => d.count));
  const w = 100 / Math.max(data.length, 1);
  return (
    <figure>
      <svg viewBox="0 0 100 40" className="h-32 w-full" role="img" aria-label={`${label}: ${data.map((d) => `${d.date} ${d.count}`).join(", ")}`} preserveAspectRatio="none">
        {data.map((d, i) => {
          const h = (d.count / max) * 34;
          return <rect key={d.date} x={i * w + w * 0.15} y={38 - h} width={w * 0.7} height={Math.max(h, d.count ? 0.8 : 0.3)} rx={0.6} fill="rgb(var(--accent))" opacity={d.count ? 1 : 0.25} />;
        })}
      </svg>
      <figcaption className="mt-1 flex justify-between text-[11px] text-mute"><span>{data[0]?.date.slice(5)}</span><span>peak {max > 1 || data.some((d) => d.count) ? max : 0}</span><span>{data[data.length - 1]?.date.slice(5)}</span></figcaption>
    </figure>
  );
}
