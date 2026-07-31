export default function Loading() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-5">
            <div className="h-3 w-20 bg-[var(--border)] rounded mb-2" />
            <div className="h-7 w-24 bg-[var(--border)] rounded" />
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-[var(--card)] border border-[var(--border)] rounded-xl p-6 h-80" />
        <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-6 h-80" />
      </div>
      <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-6 h-48" />
    </div>
  );
}
