import { AlertCircle, Check, Info, X } from "lucide-react";
import type { BlockingModal } from "../types";

export function ConfirmModal({ modal, onClose }: { modal: BlockingModal | null; onClose: () => void }) {
  if (!modal) return null;

  const tone = modal.tone ?? "info";
  const Icon = tone === "success" ? Check : tone === "warning" ? AlertCircle : Info;

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className={`modal-card tone-${tone === "warning" ? "high" : tone === "success" ? "moderate" : "offline"}`}>
        <button type="button" className="modal-close" onClick={() => { modal.onCancel?.(); onClose(); }} aria-label="Close">
          <X size={16} />
        </button>
        <div className="modal-icon">
          <Icon size={20} />
        </div>
        <h3>{modal.title}</h3>
        <p>{modal.message}</p>
        <div className="modal-actions">
          {modal.cancelLabel && (
            <button
              type="button"
              className="btn-ghost"
              onClick={() => { modal.onCancel?.(); onClose(); }}
            >
              {modal.cancelLabel}
            </button>
          )}
          <button
            type="button"
            className="btn-primary"
            onClick={async () => {
              await modal.onConfirm?.();
              onClose();
            }}
          >
            {modal.confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
