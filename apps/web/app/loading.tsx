export default function LoadingPage() {
  return (
    <main className="page-shell" aria-busy="true" aria-label="正在载入">
      <div className="loading-block" />
      <div className="loading-block short" />
    </main>
  );
}

