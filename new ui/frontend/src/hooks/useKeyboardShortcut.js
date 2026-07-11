import { useEffect } from "react";
import { isEditableTarget } from "../utils/clipboard.js";

export function useKeyboardShortcut(key, handler, { meta = true, ctrl = false, allowInInput = true } = {}) {
  useEffect(() => {
    function onKey(e) {
      if (!allowInInput && isEditableTarget(e.target)) return;
      const modOk = (meta && (e.metaKey || e.ctrlKey)) || (ctrl && e.ctrlKey) || (!meta && !ctrl);
      if (modOk && e.key.toLowerCase() === key.toLowerCase()) {
        e.preventDefault();
        handler();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [key, handler, meta, ctrl, allowInInput]);
}
