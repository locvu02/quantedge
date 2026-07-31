export default function Loading() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="flex items-center justify-between">
        <div className="h-8 w-40 bg-[var(--border)] rounded" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-6">
            <div className="h-5 w-24 bg-[var(--border)] rounded mb-4" />
            <div className="space-y-2">
              <div className="h-3 w-full bg-[var(--border)] rounded" />
              <div className="h-3 w-3/4 bg-[var(--border)] rounded" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
