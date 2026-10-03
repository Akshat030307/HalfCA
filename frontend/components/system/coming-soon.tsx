import { ApiStatus } from "./api-status";

/** Placeholder body for screens that are not built yet. */
export function ComingSoon({ milestone, items }: { milestone: string; items: string[] }) {
  return (
    <section className="card halftone relative overflow-hidden p-8">
      <div className="max-w-2xl">
        <div className="inline-block -rotate-2 rounded-full border-2 border-ink bg-orange px-4 py-1 font-heading text-sm font-bold text-on-orange dark:border-orange">
          Under construction · {milestone}
        </div>
        <h2 className="mt-5 font-display text-5xl uppercase leading-[0.95] text-ink">
          Nothing fishy here.
          <br />
          <span className="text-orange">Yet.</span>
        </h2>
        <ul className="mt-6 space-y-2 text-[15px] text-muted">
          {items.map((item) => (
            <li key={item} className="flex gap-2">
              <span className="text-orange">●</span>
              {item}
            </li>
          ))}
        </ul>
        <div className="mt-8">
          <ApiStatus />
        </div>
      </div>
    </section>
  );
}
