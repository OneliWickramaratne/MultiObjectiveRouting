import { Hammer } from "lucide-react";

export function PlaceholderPage({ title }: { title: string }) {
  return (
    <div className="page">
      <div className="rebuild-notice">
        <Hammer size={22} style={{ marginBottom: 10, color: "var(--text-faint)" }} />
        <h3>{title} is being rebuilt next</h3>
        <p>
          The foundation (routing, design system, and the Overview dashboard) is in place.
          This screen still runs on the legacy layout logic and will be redesigned in the
          next pass.
        </p>
      </div>
    </div>
  );
}
