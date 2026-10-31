export function Loading({ label = "加载中…" }: { label?: string }) {
  return <p className="muted">{label}</p>;
}

export function EmptyState({ text }: { text: string }) {
  return <div className="empty">{text}</div>;
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="error">
      <div>{message}</div>
      {onRetry ? (
        <div style={{ marginTop: 8 }}>
          <button className="secondary" onClick={onRetry}>
            重试
          </button>
        </div>
      ) : null}
    </div>
  );
}
