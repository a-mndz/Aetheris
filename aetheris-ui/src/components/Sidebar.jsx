import { motion, AnimatePresence } from 'framer-motion';
import { Plus, MessageSquare, Trash2, X } from 'lucide-react';
import TriadMark from './TriadMark';

export default function Sidebar({ conversations, activeId, onSelect, onNew, onDelete, open, onClose }) {
  const list = Object.values(conversations).sort((a, b) => b.createdAt - a.createdAt);

  const sidebarContent = (
    <>
      <div className="mb-4 flex items-center gap-2 px-1">
        <TriadMark size={20} />
        <span className="text-sm font-semibold tracking-wide text-slate-200">Aetheris</span>
        {/* Close button visible only on mobile */}
        <button
          onClick={onClose}
          className="ml-auto md:hidden text-slate-400 hover:text-slate-200 transition-colors"
          aria-label="Close sidebar"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <button
        onClick={() => { onNew(); onClose?.(); }}
        className="mb-3 flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-200 ring-1 ring-white/10 hover:bg-white/5 transition-colors"
      >
        <Plus className="h-4 w-4" />
        New conversation
      </button>

      <div className="flex-1 space-y-1 overflow-y-auto">
        {list.map((c) => (
          <div
            key={c.id}
            onClick={() => { onSelect(c.id); onClose?.(); }}
            className={`group flex cursor-pointer items-center gap-2 rounded-xl px-3 py-2.5 text-sm transition-colors ${
              c.id === activeId ? 'bg-white/8 text-slate-100' : 'text-slate-400 hover:bg-white/5'
            }`}
          >
            <MessageSquare className="h-3.5 w-3.5 flex-shrink-0" />
            <span className="flex-1 truncate">{c.title}</span>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDelete(c.id);
              }}
              aria-label="Delete conversation"
              className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-rose-400 transition-opacity"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>

      <div className="mt-3 rounded-xl glass-panel px-3 py-2.5 text-[11px] text-slate-500">
        Conversations are stored locally in this browser.
      </div>

      <div className="mt-3 border-t border-white/5 pt-3">
        <div className="flex items-center justify-between rounded-xl px-2 py-1.5 text-xs text-slate-400">
          <span className="truncate max-w-[140px] text-slate-300 font-medium" title={localStorage.getItem('user_email') || 'User'}>
            {localStorage.getItem('user_email') || 'User'}
          </span>
          <button
            onClick={() => {
              localStorage.removeItem('access_token');
              localStorage.removeItem('user_email');
              window.location.href = '/login';
            }}
            className="text-slate-400 hover:text-rose-400 transition-colors flex items-center gap-1 font-semibold cursor-pointer"
          >
            Log Out
          </button>
        </div>
      </div>
    </>
  );

  return (
    <>
      {/* Desktop Sidebar — always visible */}
      <aside className="hidden md:flex w-64 flex-col border-r border-white/5 bg-surface-800/60 p-3">
        {sidebarContent}
      </aside>

      {/* Mobile Sidebar — overlay */}
      <AnimatePresence>
        {open && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={onClose}
              className="fixed inset-0 z-40 bg-black/50 md:hidden"
            />
            <motion.aside
              initial={{ x: '-100%' }}
              animate={{ x: 0 }}
              exit={{ x: '-100%' }}
              transition={{ type: 'spring', stiffness: 300, damping: 32 }}
              className="fixed left-0 top-0 z-50 h-full w-72 flex flex-col border-r border-white/10 bg-surface-800/95 p-3 backdrop-blur-xl md:hidden"
            >
              {sidebarContent}
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
