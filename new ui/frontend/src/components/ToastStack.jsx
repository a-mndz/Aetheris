import { AlertTriangle, Check } from "lucide-react";

export default function ToastStack({ toasts }) {
  return (
    <div className="toast-stack" aria-live="polite" role="status">
      {toasts.map((toast) => (
        <div className={`toast${toast.kind === "error" ? " error" : ""}`} key={toast.id}>
          {toast.kind === "error" ? <AlertTriangle size={14} /> : <Check size={14} />}
          <span>{toast.text}</span>
          {toast.action && <button className="toast-action" onClick={toast.action.onClick}>{toast.action.label}</button>}
        </div>
      ))}
    </div>
  );
}
