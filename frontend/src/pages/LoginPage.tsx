import { LoginForm } from "../features/auth/LoginForm";

export default function LoginPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-base">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">
            HardWorkers AI
          </h1>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            Sign in to your assistant
          </p>
        </div>
        <LoginForm />
      </div>
    </div>
  );
}
