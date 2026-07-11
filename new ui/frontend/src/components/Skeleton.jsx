export default function Skeleton({ width = "100%", height = "12px", marginTop = 0 }) {
  return <div className="skeleton" style={{ width, height, marginTop }} />;
}

export function ConversationListSkeleton() {
  return (
    <div className="conv-list" aria-hidden="true">
      {Array.from({ length: 5 }).map((_, i) => (
        <div className="conv-item" key={i}>
          <Skeleton width="85%" height="11px" />
          <Skeleton width="40%" height="9px" marginTop={6} />
        </div>
      ))}
    </div>
  );
}

export function StatTileSkeleton() {
  return (
    <div className="stat-tile">
      <Skeleton width="60%" height="9px" />
      <Skeleton width="70%" height="14px" marginTop={6} />
    </div>
  );
}
