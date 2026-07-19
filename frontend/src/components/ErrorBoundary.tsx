import { Component } from "react";
import type { ReactNode } from "react";
import { AlertTriangle } from "lucide-react";

type Props = { children: ReactNode; fallbackTitle: string };
type State = { error: Error | null };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error) {
    // eslint-disable-next-line no-console
    console.error("Caught by ErrorBoundary:", error);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="card empty-state" style={{ padding: "40px 20px", display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
          <AlertTriangle size={20} style={{ color: "var(--status-critical)" }} />
          <div style={{ color: "var(--text)" }}>{this.props.fallbackTitle}</div>
          <div style={{ fontSize: 12, color: "var(--text-faint)", maxWidth: 420, textAlign: "center" }}>
            {this.state.error.message || "An unexpected error occurred while rendering this view."}
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
