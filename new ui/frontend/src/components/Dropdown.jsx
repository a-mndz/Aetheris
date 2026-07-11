import { ChevronDown, Check } from "lucide-react";
import Popover from "./Popover.jsx";

export default function Dropdown({ icon: Icon, value, options, onChange, align = "left", direction = "down" }) {
  return (
    <Popover align={align} direction={direction}
      renderTrigger={({ open, triggerRef, toggle }) => (
        <button ref={triggerRef} type="button" className="dd-trigger" onClick={toggle} aria-haspopup="listbox" aria-expanded={open}>
          {Icon && <Icon size={14} />}
          <span>{value}</span>
          <ChevronDown size={13} className={`dd-chev${open ? " up" : ""}`} />
        </button>
      )}>
      {({ close }) => (
        <ul className="dd-list" role="listbox">
          {options.map((opt) => (
            <li key={opt} role="option" aria-selected={opt === value}
              className={`dd-item${opt === value ? " active" : ""}`}
              onClick={() => { onChange(opt); close(); }}>
              <span className="dd-check">{opt === value && <Check size={13} />}</span>
              <span>{opt}</span>
            </li>
          ))}
        </ul>
      )}
    </Popover>
  );
}
