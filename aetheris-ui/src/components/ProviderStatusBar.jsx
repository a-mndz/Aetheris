import { Activity, Menu } from 'lucide-react';

const STATUS_COLOR = {
  online: 'bg-emerald-400',
  degraded: 'bg-amber-400',
  offline: 'bg-rose-400',
  unknown: 'bg-slate-500',
};

const STATUS_LABEL = {
  online: 'Online',
  degraded: 'Degraded',
  offline: 'Offline',
  unknown: 'Unknown',
};

export default function ProviderStatusBar({ providers, onToggleTelemetry, onToggleSidebar }) {
  return (
    <header className="flex items-center justify-between border-b border-white/5 bg-surface-800/40 px-4 py-2.5 md:px-8">
      {/* Left: Hamburger (mobile) + Title */}
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleSidebar}
          className="md:hidden text-slate-400 hover:text-slate-200 transition-colors"
          aria-label="Open sidebar"
        >
          <Menu className="h-5 w-5" />
        </button>
        <span className="text-sm font-semibold text-slate-200 md:hidden">Aetheris</span>
        <span className="hidden md:inline text-xs text-slate-500">
          Adaptive Multi-Model Reasoning Orchestrator
        </span>
      </div>

      {/* Right: Providers + Telemetry */}
      <div className="flex items-center gap-4">
        <div className="hidden sm:flex items-center gap-3">
          {providers.map((p) => (
            <span
              key={p.name}
              className="flex items-center gap-1.5 text-xs text-slate-400"
              title={`${p.name}: ${p.status}`}
            >
              <span
                className={`h-2.5 w-2.5 rounded-full ${STATUS_COLOR[p.status] ?? STATUS_COLOR.unknown} ${
                  p.status === 'online' ? 'animate-pulse-slow' : ''
                } ring-2 ring-black/20`}
              />
              <span className="hidden lg:inline">{p.name}</span>
              <span className="lg:hidden text-[10px]">{p.name?.split(' ')[0]}</span>
            </span>
          ))}
        </div>
        <button
          onClick={onToggleTelemetry}
          className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium text-slate-300 ring-1 ring-white/10 hover:bg-white/5 transition-colors"
        >
          <Activity className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">Telemetry</span>
        </button>
      </div>
    </header>
  );
}
