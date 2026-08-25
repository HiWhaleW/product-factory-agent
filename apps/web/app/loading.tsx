export default function LoadingPage() {
  return (
    <main className="page-shell" aria-busy="true" aria-label="正在载入" id="main-content">
      <div className="loading-block" />
      <div className="loading-block short" />
    </main>
  );
}
