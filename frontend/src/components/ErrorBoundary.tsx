import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ErrorBoundary caught:", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback || (
          <div className="flex flex-col items-center justify-center gap-2 p-8">
            <p className="text-[var(--error)]">Something went wrong</p>
            <button
              onClick={() => this.setState({ hasError: false })}
              className="rounded-md bg-primary px-3 py-1 text-sm text-white"
            >
              Retry
            </button>
          </div>
        )
      );
    }
    return this.props.children;
  }
}
