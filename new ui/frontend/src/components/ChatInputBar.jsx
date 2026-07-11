import { useRef, useEffect } from "react";
import { Paperclip, X, Globe, Send, Square, Scale, Cpu } from "lucide-react";
import Dropdown from "./Dropdown.jsx";

const MAX_CHARS = 4000;

function ChatInputBar({
  value, onChange, onSend, onStop, streaming, mode, setMode, modelSelect, setModelSelect,
  webSearch, setWebSearch, autoExpand, setAutoExpand, attached, setAttached, pushToast, inputRef,
}) {
  const fileRef = useRef(null);

  useEffect(() => {
    const ta = inputRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
  }, [value, inputRef]);

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (!streaming) onSend(); }
  }
  function handleFile(e) {
    const f = e.target.files?.[0];
    if (f) { setAttached(f.name); pushToast(`Attached ${f.name}`); }
    e.target.value = "";
  }
  const overLimit = value.length > MAX_CHARS;

  return (
    <div className="input-bar">
      <div className="input-bar-inner">
        {attached && (
          <div className="attach-chip">
            <Paperclip size={12} /> <span className="fname">{attached}</span>
            <button onClick={() => setAttached(null)} aria-label="Remove attachment"><X size={12} /></button>
          </div>
        )}
        <div className="input-row">
          <label htmlFor="aetheris-input" className="sr-only">Ask Aetheris anything</label>
          <textarea
            id="aetheris-input"
            ref={inputRef}
            rows={1}
            placeholder="Ask Aetheris anything..."
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            aria-label="Message Aetheris"
          />
          {streaming ? (
            <button className="send-btn stop" onClick={onStop} aria-label="Stop generating">
              <Square size={14} fill="currentColor" />
            </button>
          ) : (
            <button className="send-btn" onClick={onSend} disabled={!value.trim() || overLimit} aria-label="Send message">
              <Send size={16} />
            </button>
          )}
        </div>
        <div className="input-controls">
          <Dropdown icon={Scale} value={mode} options={["Balanced", "Fast", "Deep"]} onChange={setMode} direction="up" />
          <Dropdown icon={Cpu} value={modelSelect} options={["Auto", "Manual"]} onChange={setModelSelect} direction="up" />
          <input type="file" ref={fileRef} hidden onChange={handleFile} aria-label="Attach a file" />
          <button className="text-btn" onClick={() => fileRef.current?.click()}><Paperclip size={14} /> Attach</button>
          <button className={`text-btn${webSearch ? " on" : ""}`} onClick={() => setWebSearch((w) => !w)}>
            <Globe size={14} /> Web Search {webSearch ? "On" : "Off"}
          </button>
          <span className={`char-count${overLimit ? " near-limit" : ""}`}>{value.length}/{MAX_CHARS}</span>
          <div className="spacer" />
          <div className="switch-row">
            <span>Auto-Expand Reasoning</span>
            <button
              type="button"
              className={`switch${autoExpand ? " on" : ""}`}
              onClick={() => setAutoExpand((a) => !a)}
              role="switch"
              aria-checked={autoExpand}
              aria-label={`Auto-Expand Reasoning ${autoExpand ? "on" : "off"}`}
            />
          </div>
        </div>
        <div className="input-hint">Enter to send // Shift+Enter for newline // <kbd>/</kbd> to focus</div>
      </div>
    </div>
  );
}

export default ChatInputBar;
export { MAX_CHARS };
