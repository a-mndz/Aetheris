import { useState, useRef } from 'react';
import { ArrowUp, Loader2 } from 'lucide-react';

export default function InputBox({ onSend, disabled }) {
  const [value, setValue] = useState('');
  const textareaRef = useRef(null);

  const submit = () => {
    if (!value.trim() || disabled) return;
    onSend(value);
    setValue('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const autoGrow = (e) => {
    setValue(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
  };

  const charCount = value.length;

  return (
    <div className="border-t border-white/5 bg-surface-900/60 px-4 py-4 md:px-8">
      <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-2xl glass-panel input-glow px-3 py-2.5 transition-shadow duration-300">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={autoGrow}
          onKeyDown={handleKeyDown}
          rows={1}
          placeholder="Ask Aetheris anything…"
          className="flex-1 resize-none bg-transparent text-sm text-slate-100 placeholder:text-slate-500 outline-none max-h-40"
        />
        <div className="flex items-center gap-2 flex-shrink-0">
          {charCount > 0 && (
            <span className="text-[10px] text-slate-600 font-mono tabular-nums">
              {charCount}
            </span>
          )}
          <button
            onClick={submit}
            disabled={disabled || !value.trim()}
            aria-label="Send query"
            className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-cyan-500 to-violet-500 text-white transition-all disabled:opacity-30 hover:shadow-glow active:scale-95"
          >
            {disabled ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4" />}
          </button>
        </div>
      </div>
      <p className="mx-auto mt-2 max-w-3xl text-center text-[11px] text-slate-500">
        Aetheris reasons through a Logician and a Creative agent, reconciled by a Judge. Verify high-stakes answers independently.
      </p>
    </div>
  );
}
