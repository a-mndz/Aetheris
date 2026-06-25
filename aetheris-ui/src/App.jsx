import { useEffect, useState, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import ChatWindow from './components/ChatWindow';
import InputBox from './components/InputBox';
import ProviderStatusBar from './components/ProviderStatusBar';
import TelemetryDrawer from './components/TelemetryDrawer';
import { useChatStore } from './store/useChatStore';
import { useSendQuery } from './hooks/useSendQuery';
import { fetchProviderStatus } from './api/client';

const HEALTH_POLL_INTERVAL = 30000; // 30 seconds

export default function App() {
  // Auth check — must be before any hooks to satisfy React rules
  const [isAuthenticated, setIsAuthenticated] = useState(() => {
    return !!localStorage.getItem('access_token');
  });

  const conversations = useChatStore((s) => s.conversations);
  const activeId = useChatStore((s) => s.activeId);
  const telemetry = useChatStore((s) => s.telemetry);
  const providerHealth = useChatStore((s) => s.providerHealth);
  const setProviderHealth = useChatStore((s) => s.setProviderHealth);
  const newConversation = useChatStore((s) => s.newConversation);
  const selectConversation = useChatStore((s) => s.selectConversation);
  const deleteConversation = useChatStore((s) => s.deleteConversation);

  const { send, stage, agentStates, partialData } = useSendQuery();
  const [telemetryOpen, setTelemetryOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const activeConversation = conversations[activeId];
  const pending = stage !== 'idle' && stage !== 'done' && stage !== 'error';

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!isAuthenticated) {
      window.location.href = '/login';
    }
  }, [isAuthenticated]);

  // Poll real provider health from /api/status
  // Only poll when authenticated — prevents 401 noise
  useEffect(() => {
    if (!isAuthenticated) return;

    let active = true;

    const poll = async () => {
      const data = await fetchProviderStatus();
      if (!active) return;

      if (data?.providers && Array.isArray(data.providers)) {
        // Map backend provider data to the UI format
        const mapped = data.providers.map((p) => ({
          name: typeof p === 'string' ? p : (p.name || p.provider || 'Unknown'),
          status: typeof p === 'string' ? 'online' : (p.status || 'online'),
        }));
        if (mapped.length > 0) {
          setProviderHealth(mapped);
          return;
        }
      }

      // Fallback: show default providers as unknown status when backend is unreachable
      setProviderHealth([
        { name: 'Groq', status: 'unknown' },
        { name: 'OpenRouter', status: 'unknown' },
        { name: 'Local Fallback', status: 'unknown' },
      ]);
    };

    poll();
    const interval = setInterval(poll, HEALTH_POLL_INTERVAL);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [isAuthenticated, setProviderHealth]);

  const handleSend = useCallback((text) => send(activeId, text), [send, activeId]);
  const closeSidebar = useCallback(() => setSidebarOpen(false), []);

  // Don't render the app until authenticated
  if (!isAuthenticated) {
    return null;
  }

  return (
    <div className="flex h-screen overflow-hidden bg-gradient-to-br from-surface-900 via-surface-900 to-[#0c0a1a] text-slate-100">
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={selectConversation}
        onNew={newConversation}
        onDelete={deleteConversation}
        open={sidebarOpen}
        onClose={closeSidebar}
      />
      <div className="flex flex-1 flex-col min-w-0">
        <ProviderStatusBar
          providers={providerHealth}
          onToggleTelemetry={() => setTelemetryOpen(true)}
          onToggleSidebar={() => setSidebarOpen(true)}
        />
        <ChatWindow
          messages={activeConversation?.messages ?? []}
          currentStage={stage}
          agentStates={agentStates}
          partialData={partialData}
          onSuggestion={handleSend}
        />
        <InputBox onSend={handleSend} disabled={pending} />
      </div>
      <TelemetryDrawer
        open={telemetryOpen}
        onClose={() => setTelemetryOpen(false)}
        telemetry={telemetry}
      />
    </div>
  );
}
