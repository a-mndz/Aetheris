import { useEffect } from "react";

export function useClickOutside(ref, onOutside) {
  useEffect(() => {
    function handle(e) { if (ref.current && !ref.current.contains(e.target)) onOutside(); }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [ref, onOutside]);
}
