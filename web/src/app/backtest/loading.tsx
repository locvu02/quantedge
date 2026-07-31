export default function Loading() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="flex items-center gap-4">
        <div className="h-8 w-48 bg-[var(--border)] rounded" />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[...Array(8)].map((_, i) => (
          <div key={i} className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4">
            <div className="h-3 w-16 bg-[var(--border)] rounded mb-2" />
            <div className="h-6 w-20 bg-[var(--border)] rounded" />
          </div>
        ))}
      </div>
      <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-6 h-80" />
    </div>
  );
}
