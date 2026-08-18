import { useRef, useState } from "react";
import { useClickOutside } from "../hooks/useClickOutside.js";
import { useEscapeKey } from "../hooks/useEscapeKey.js";

export default function Popover({ align = "right", direction = "down", menuClassName = "", renderTrigger, children }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const triggerRef = useRef(null);

  function closePopover() {
    setOpen(false);
  }

  useClickOutside(wrapRef, () => setOpen(false));
  useEscapeKey(() => { if (open) closePopover(); });

  return (
    <div className="dd" ref={wrapRef}>
      {renderTrigger({ open, triggerRef, toggle: () => setOpen((o) => !o) })}
      {open && (
        <div className={`dd-menu align-${align} ${direction === "up" ? "direction-up" : ""} ${menuClassName}`}>
          {children({ close: closePopover })}
        </div>
      )}
    </div>
  );
}
