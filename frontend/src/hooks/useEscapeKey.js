import { useEffect } from "react";

export function useEscapeKey(onEscape) {
  useEffect(() => {
    function handle(e) { if (e.key === "Escape") onEscape(); }
    document.addEventListener("keydown", handle);
    return () => document.removeEventListener("keydown", handle);
  }, [onEscape]);
}
