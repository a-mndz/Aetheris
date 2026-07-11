import { useState, useRef } from "react";
import { useClickOutside } from "../hooks/useClickOutside.js";
import { useEscapeKey } from "../hooks/useEscapeKey.js";

export default function Popover({ align = "right", direction = "down", menuClassName = "", renderTrigger, children }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const triggerRef = useRef(null);

  function closeAndRefocus() {
    setOpen(false);
    triggerRef.current?.focus();
  }

  useClickOutside(wrapRef, () => setOpen(false));
  useEscapeKey(() => { if (open) closeAndRefocus(); });

  return (
    <div className="dd" ref={wrapRef}>
      {renderTrigger({ open, triggerRef, toggle: () => setOpen((o) => !o) })}
      {open && (
        <div className={`dd-menu align-${align} ${direction === "up" ? "direction-up" : ""} ${menuClassName}`}>
          {children({ close: closeAndRefocus })}
        </div>
      )}
    </div>
  );
}
