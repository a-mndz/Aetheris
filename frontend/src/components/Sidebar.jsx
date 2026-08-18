import { memo, useState, useEffect, useRef } from "react";
import { Search, Plus, X, Trash2, Check, Activity, PanelLeftClose } from "lucide-react";
import { useDebouncedValue } from "../hooks/useDebouncedValue.js";
import { useFocusTrap } from "../hooks/useFocusTrap.js";
import { DEFAULT_DEBOUNCE_DELAY } from "../constants/timing.js";
import { NAV_ITEMS } from "../constants/nav.js";
import { getScoreTone } from "../utils/format.js";
import { ConversationListSkeleton } from "./Skeleton.jsx";

const Sidebar = memo(function Sidebar({ open, conversations, activeId, onSelect, onDelete, onNew, search, setSearch, view, setView, searchRef, loading, isNarrow, streaming, onClose }) {
  const [localSearch, setLocalSearch] = useState(search);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const debouncedSearch = useDebouncedValue(localSearch, DEFAULT_DEBOUNCE_DELAY);
  const filtered = conversations.filter((c) => c.title.toLowerCase().includes(debouncedSearch.toLowerCase()));
  const innerRef = useRef(null);
  const deleteTimerRef = useRef(null);
  const itemRefs = useRef([]);

  useEffect(() => {
    setLocalSearch(search);
  }, [search]);

  useEffect(() => {
    if (debouncedSearch !== search) setSearch(debouncedSearch);
  }, [debouncedSearch, search, setSearch]);

  useEffect(() => () => clearTimeout(deleteTimerRef.current), []);

  useEffect(() => {
    if (!confirmDeleteId) return;
    if (!conversations.some((c) => c.id === confirmDeleteId)) setConfirmDeleteId(null);
  }, [confirmDeleteId, conversations]);

  useEffect(() => {
    const activeIndex = filtered.findIndex((c) => c.id === activeId);
    if (activeIndex >= 0) setFocusedIndex(activeIndex);
    else if (filtered.length === 0) setFocusedIndex(-1);
    else if (focusedIndex >= filtered.length) setFocusedIndex(filtered.length - 1);
  }, [activeId, filtered, focusedIndex]);

  useEffect(() => {
    const activeIndex = filtered.findIndex((c) => c.id === activeId);
    if (activeIndex < 0) return;
    itemRefs.current[activeIndex]?.scrollIntoView({ block: "nearest" });
  }, [activeId, filtered]);

  function queueDeleteConfirm(id) {
    clearTimeout(deleteTimerRef.current);
    setConfirmDeleteId(id);
    deleteTimerRef.current = setTimeout(() => {
      setConfirmDeleteId((currentId) => (currentId === id ? null : currentId));
    }, 3000);
  }

  function clearDeleteConfirm() {
    clearTimeout(deleteTimerRef.current);
    setConfirmDeleteId(null);
  }

  function focusConversation(index) {
    const next = filtered[index];
    if (!next) return;
    setFocusedIndex(index);
    itemRefs.current[index]?.focus();
  }

  function selectConversation(conv, index) {
    setFocusedIndex(index);
    onSelect(conv);
    setTimeout(() => itemRefs.current[index]?.scrollIntoView({ block: "nearest" }), 0);
  }

  function handleListKeyDown(e) {
    if (!filtered.length) return;
    const currentIndex = focusedIndex >= 0 ? focusedIndex : Math.max(filtered.findIndex((c) => c.id === activeId), 0);

    if (e.key === "ArrowDown") {
      e.preventDefault();
      focusConversation(Math.min(currentIndex + 1, filtered.length - 1));
      return;
    }

    if (e.key === "ArrowUp") {
      e.preventDefault();
      focusConversation(Math.max(currentIndex - 1, 0));
      return;
    }

    if (e.key === "Home") {
      e.preventDefault();
      focusConversation(0);
      return;
    }

    if (e.key === "End") {
      e.preventDefault();
      focusConversation(filtered.length - 1);
      return;
    }

    if (e.key === "Enter" && e.target === e.currentTarget) {
      e.preventDefault();
      const conv = filtered[currentIndex];
      if (conv) selectConversation(conv, currentIndex);
    }
  }

  useFocusTrap(open && isNarrow, innerRef);
  return (
    <aside className={`sidebar${open ? "" : " collapsed"}`} inert={!open} aria-hidden={!open}>
      <div className="sidebar-inner" ref={innerRef}>
        {isNarrow && (
          <div className="panel-mobile-head">
            <div className="panel-mobile-title">Conversations</div>
            <button type="button" className="icon-btn panel-close-btn" onClick={onClose} aria-label="Close conversations panel">
              <PanelLeftClose size={16} />
            </button>
          </div>
        )}
        <button className="btn-primary full" onClick={onNew}><Plus size={15} /> New Conversation</button>
        <div className="new-conv-hint"><kbd>⌘N</kbd> to start a new conversation</div>

        <div className="search-box">
          <Search size={14} />
          <label htmlFor="conv-search" className="sr-only">Search conversations</label>
          <input id="conv-search" ref={searchRef} placeholder="Search conversations..." value={localSearch} onChange={(e) => setLocalSearch(e.target.value)} />
          {localSearch.length > 0 && <button className="search-clear" onClick={() => setLocalSearch("")} aria-label="Clear search"><X size={12} /></button>}
          <kbd>⌘K</kbd>
        </div>

        <div className="sidebar-label">Recent Conversations</div>
        {loading ? (
          <ConversationListSkeleton />
        ) : (
          <div className="conv-list" role="listbox" tabIndex={filtered.length ? 0 : -1} aria-label="Recent conversations" onKeyDown={handleListKeyDown}>
            {filtered.length === 0 && (
              <div className="empty-note">
                <Search size={20} className="empty-note-icon" />
                <div>No conversations match "{debouncedSearch}"</div>
              </div>
            )}
            {filtered.map((c, index) => {
              const isConfirmingDelete = confirmDeleteId === c.id;
              return (
                <div key={c.id} className={`conv-item${c.id === activeId ? " active" : ""}${index === focusedIndex ? " focused" : ""}`}>
                  <button
                    ref={(node) => { itemRefs.current[index] = node; }}
                    className="conv-main"
                    onClick={() => selectConversation(c, index)}
                    onFocus={() => setFocusedIndex(index)}
                    role="option"
                    aria-selected={c.id === activeId}
                  >
                    <div className="conv-title">{c.title}</div>
                    <div className="conv-meta">
                      <div className="conv-time">{c.time}</div>
                      {c.score != null && <span className={`conv-score ${getScoreTone(c.score)}`}>{c.score}%</span>}
                    </div>
                  </button>
                  <div className="conv-actions">
                    {isConfirmingDelete ? (
                      <>
                        <button className="conv-confirm" onClick={() => { clearDeleteConfirm(); onDelete(c.id); }} aria-label={`Confirm delete ${c.title}`}>
                          <Check size={11} /> Delete?
                        </button>
                        <button className="conv-danger-btn" onClick={clearDeleteConfirm} aria-label={`Cancel delete ${c.title}`}>
                          <X size={11} />
                        </button>
                      </>
                    ) : (
                      <button className="conv-danger-btn" onClick={() => queueDeleteConfirm(c.id)} aria-label={`Delete ${c.title}`}>
                        <Trash2 size={11} />
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {streaming && <div className="generating-indicator"><Activity size={12} /> Generating...</div>}

        <nav className="sidebar-nav" aria-label="Main navigation">
          {NAV_ITEMS.map((n) => (
            <button key={n.id} className={`nav-item${view === n.id ? " active" : ""}`} onClick={() => setView(n.id)} disabled={streaming}>
              <n.icon size={16} /> {n.name}
            </button>
          ))}
        </nav>
      </div>
    </aside>
  );
});

export default Sidebar;
