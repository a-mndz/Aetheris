import { useEffect } from "react";

export function useFocusTrap(active, containerRef) {
  useEffect(() => {
    if (!active || !containerRef.current) return;
    const node = containerRef.current;
    const selector = 'button, [href], input, textarea, select, [tabindex]:not([tabindex="-1"])';
    const handle = (e) => {
      if (e.key !== "Tab") return;
      const focusables = node.querySelectorAll(selector);
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    node.addEventListener("keydown", handle);
    return () => node.removeEventListener("keydown", handle);
  }, [active, containerRef]);
}
