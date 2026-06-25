import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Clock, Gauge, AlertTriangle, Server } from 'lucide-react';

function Stat({ label, value, icon: Icon }) {
  return (
    <div className="rounded-xl glass-panel p-3">
      <div className="flex items-center gap-1.5 mb-1">
        {Icon && <Icon className="h-3 w-3 text-slate-500" />}
        <p className="text-[11px] text-slate-500">{label}</p>
      </div>
      <p className="text-lg font-semibold text-slate-100">{value}</p>
    </div>
  );
}

function formatLatency(ms) {
  if (ms == null || isNaN(ms)) return '—';
  if (ms < 1000) return `${ms}ms`;
  const totalSeconds = ms / 1000;
  if (totalSeconds >= 60) {
    const roundedSeconds = Math.round(totalSeconds);
    const minutes = Math.floor(roundedSeconds / 60);
    const seconds = roundedSeconds % 60;
    return `${minutes}m ${seconds}s`;
  }
  return `${totalSeconds.toFixed(1)}s`;
}

export default function TelemetryDrawer({ open, onClose, telemetry }) {
  const totalCalls = telemetry.length;
  const avgLatencyVal = totalCalls
    ? Math.round(telemetry.reduce((sum, t) => sum + (t.latencyMs || 0), 0) / totalCalls)
    : 0;
  const avgLatency = formatLatency(avgLatencyVal);
  const avgConfidence = totalCalls
    ? (telemetry.reduce((sum, t) => sum + (t.confidence ?? 0), 0) / totalCalls * 100).toFixed(0)
    : 0;

  // Escape key handler
  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-40 bg-black/40"
          />
          <motion.aside
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 300, damping: 32 }}
            className="fixed right-0 top-0 z-50 h-full w-full max-w-sm border-l border-white/10 bg-surface-800/95 p-5 backdrop-blur-xl overflow-y-auto"
          >
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-sm font-semibold text-slate-200">Telemetry Dashboard</h3>
              <button
                onClick={onClose}
                aria-label="Close telemetry panel"
                className="text-slate-400 hover:text-slate-200 transition-colors rounded-lg p-1 hover:bg-white/5"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="grid grid-cols-3 gap-2 mb-4">
              <Stat icon={Server} label="API calls" value={totalCalls} />
              <Stat icon={Clock} label="Avg latency" value={avgLatency} />
              <Stat icon={Gauge} label="Avg conf." value={`${avgConfidence}%`} />
            </div>

            <div className="space-y-2" style={{ maxHeight: 'calc(100vh - 220px)', overflowY: 'auto' }}>
              {telemetry.length === 0 && (
                <div className="text-center py-8">
                  <p className="text-sm text-slate-500">No requests yet</p>
                  <p className="text-xs text-slate-600 mt-1">Send a query to see telemetry data</p>
                </div>
              )}
              {telemetry.map((t) => (
                <div key={t.id} className="rounded-xl glass-panel p-3 text-xs">
                  <p className="truncate text-slate-300 mb-2 font-medium">{t.query}</p>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-slate-500">
                    <div className="flex justify-between">
                      <span>Latency</span>
                      <span className="text-slate-300 font-mono">{formatLatency(t.latencyMs)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Confidence</span>
                      <span className="text-slate-300 font-mono">
                        {t.confidence != null ? `${(t.confidence * 100).toFixed(0)}%` : '—'}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>Bias Risk</span>
                      <span className={`font-medium ${
                        t.biasRisk?.toLowerCase() === 'low' ? 'text-emerald-400' :
                        t.biasRisk?.toLowerCase() === 'medium' ? 'text-amber-400' :
                        t.biasRisk?.toLowerCase() === 'high' ? 'text-rose-400' : 'text-slate-400'
                      }`}>
                        {t.biasRisk ?? '—'}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>Provider</span>
                      <span className="text-slate-300">{t.provider ?? '—'}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
