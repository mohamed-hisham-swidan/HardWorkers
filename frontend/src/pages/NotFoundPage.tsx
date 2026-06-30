import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-base">
      <h1 className="text-4xl font-bold text-[var(--text-primary)]">404</h1>
      <p className="text-[var(--text-muted)]">Page not found</p>
      <Link
        to="/"
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:opacity-90"
      >
        Go Home
      </Link>
    </div>
  );
}
