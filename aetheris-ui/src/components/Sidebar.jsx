import { useMemo, useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, MessageSquare, Trash2, X, Search } from 'lucide-react';
import TriadMark from './TriadMark';

function formatConversationTimestamp(timestamp) {
  const date = new Date(timestamp);
  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const isYesterday = date.toDateString() === yesterday.toDateString();

  if (isToday) {
    return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  }
  if (isYesterday) {
    return 'Yesterday';
  }
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

function HighlightMatch({ text, query }) {
  if (!query) return text;

  const lowerText = text.toLowerCase();
  const lowerQuery = query.toLowerCase();
  const index = lowerText.indexOf(lowerQuery);

  if (index === -1) return text;

  return (
    <>
      {text.slice(0, index)}
      <mark className="rounded bg-accent-cyan/20 text-accent-cyan">{text.slice(index, index + query.length)}</mark>
      {text.slice(index + query.length)}
    </>
  );
}

function conversationMatchesQuery(conversation, query) {
  if (conversation.title.toLowerCase().includes(query)) return true;

  return conversation.messages.some((message) => {
    if (message.content?.toLowerCase().includes(query)) return true;
    return message.response?.answer?.toLowerCase().includes(query);
  });
}

export default function Sidebar({ conversations, activeId, onSelect, onNew, onDelete, open, onClose }) {
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [deleteTarget, setDeleteTarget] = useState(null);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(searchQuery.trim()), 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const filteredList = useMemo(() => {
    const sorted = Object.values(conversations).sort((a, b) => b.createdAt - a.createdAt);
    const query = debouncedQuery.toLowerCase();

    if (!query) return sorted;
    return sorted.filter((conversation) => conversationMatchesQuery(conversation, query));
  }, [conversations, debouncedQuery]);

  const handleConfirmDelete = () => {
    if (deleteTarget) {
      onDelete(deleteTarget);
      setDeleteTarget(null);
    }
  };

  const sidebarContent = (
    <>
      <div className="mb-4 flex items-center gap-2 px-1">
        <TriadMark size={20} />
        <span className="text-sm font-semibold tracking-wide text-slate-200">Aetheris</span>
        <button
          onClick={onClose}
          className="ml-auto text-slate-400 transition-colors hover:text-slate-200 md:hidden"
          aria-label="Close sidebar"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="relative mb-3">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
        <input
          type="search"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          placeholder="Search conversations..."
          aria-label="Search conversations"
          className="w-full rounded-xl border border-white/10 bg-surface-900/60 py-2 pl-9 pr-9 text-sm text-slate-200 placeholder-slate-500 focus:border-accent-cyan/40 focus:outline-none focus:ring-2 focus:ring-accent-cyan/30"
        />
        {searchQuery && (
          <button
            onClick={() => setSearchQuery('')}
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-slate-500 transition-colors hover:text-slate-200"
            aria-label="Clear search"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      <button
        onClick={() => {
          onNew();
          onClose?.();
        }}
        className="mb-3 flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-200 ring-1 ring-white/10 transition-colors hover:bg-white/5"
      >
        <Plus className="h-4 w-4" />
        New conversation
      </button>

      <div className="flex-1 space-y-1 overflow-y-auto">
        {filteredList.length === 0 ? (
          <p className="px-3 py-6 text-center text-sm text-slate-500">No results</p>
        ) : (
          filteredList.map((conversation) => (
            <div
              key={conversation.id}
              onClick={() => {
                onSelect(conversation.id);
                onClose?.();
              }}
              className={`group flex cursor-pointer items-center gap-2 rounded-xl px-3 py-2.5 text-sm transition-colors ${
                conversation.id === activeId
                  ? 'border border-accent-cyan/20 bg-accent-cyan/10 text-slate-100'
                  : 'text-slate-400 hover:bg-white/5'
              }`}
            >
              <MessageSquare className="h-3.5 w-3.5 flex-shrink-0" />
              <div className="min-w-0 flex-1">
                <span className="block truncate">
                  <HighlightMatch text={conversation.title} query={debouncedQuery} />
                </span>
                <span className="mt-0.5 block text-[11px] text-slate-500">
                  {formatConversationTimestamp(conversation.createdAt)}
                </span>
              </div>
              <button
                onClick={(event) => {
                  event.stopPropagation();
                  setDeleteTarget(conversation.id);
                }}
                aria-label="Delete conversation"
                className="text-slate-500 opacity-0 transition-opacity hover:text-rose-400 group-hover:opacity-100"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))
        )}
      </div>

      <div className="glass-panel mt-3 rounded-xl px-3 py-2.5 text-[11px] text-slate-500">
        Conversations are stored locally in this browser.
      </div>

      <div className="mt-3 border-t border-white/5 pt-3">
        <div className="flex items-center justify-between rounded-xl px-2 py-1.5 text-xs text-slate-400">
          <span
            className="max-w-[140px] truncate font-medium text-slate-300"
            title={localStorage.getItem('user_email') || 'User'}
          >
            {localStorage.getItem('user_email') || 'User'}
          </span>
          <button
            onClick={() => {
              localStorage.removeItem('access_token');
              localStorage.removeItem('user_email');
              window.location.href = '/login';
            }}
            className="flex cursor-pointer items-center gap-1 font-semibold text-slate-400 transition-colors hover:text-rose-400"
          >
            Log Out
          </button>
        </div>
      </div>
    </>
  );

  return (
    <>
      <aside className="hidden w-[280px] flex-col border-r border-white/5 bg-surface-800/60 p-3 md:flex">
        {sidebarContent}
      </aside>

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
              className="fixed left-0 top-0 z-50 flex h-full w-full flex-col border-r border-white/10 bg-surface-800/95 p-3 backdrop-blur-xl md:hidden"
            >
              {sidebarContent}
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {deleteTarget && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setDeleteTarget(null)}
              className="fixed inset-0 z-[60] bg-black/60"
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2 }}
              role="dialog"
              aria-modal="true"
              aria-labelledby="delete-dialog-title"
              className="fixed left-1/2 top-1/2 z-[70] w-[min(90vw,24rem)] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-white/10 bg-surface-800 p-5 shadow-xl"
            >
              <h2 id="delete-dialog-title" className="text-base font-semibold text-slate-100">
                Delete conversation?
              </h2>
              <p className="mt-2 text-sm text-slate-400">
                This action cannot be undone. The conversation will be permanently removed.
              </p>
              <div className="mt-5 flex justify-end gap-2">
                <button
                  onClick={() => setDeleteTarget(null)}
                  className="rounded-lg px-4 py-2 text-sm font-medium text-slate-300 transition-colors hover:bg-surface-700"
                >
                  Cancel
                </button>
                <button
                  onClick={handleConfirmDelete}
                  className="rounded-lg bg-rose-500/90 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-rose-500"
                >
                  Delete
                </button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
