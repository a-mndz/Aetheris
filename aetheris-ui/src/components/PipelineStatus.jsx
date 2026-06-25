import { motion } from 'framer-motion';
import { GitBranch, Users, Scale, CheckCircle2, Clock, Radio } from 'lucide-react';
import { useState, useEffect } from 'react';

const STAGES = [
  { key: 'breaker', label: 'Breaker', sublabel: 'Knowledge gate check', icon: GitBranch, agents: ['Breaker'] },
  { key: 'agents', label: 'Agents', sublabel: 'Logician + Creative reasoning', icon: Users, agents: ['Logician', 'Creative'] },
  { key: 'judge', label: 'Judge', sublabel: 'Synthesis & validation', icon: Scale, agents: ['Judge'] },
  { key: 'done', label: 'Done', sublabel: 'Response ready', icon: CheckCircle2, agents: [] },
];

function stageIndex(stage) {
  if (stage === 'idle' || stage === 'error') return -1;
  return STAGES.findIndex((s) => s.key === stage);
}

/**
 * Derive the latest progress message from agent states for a given stage.
 */
function getStageMessage(stageConfig, agentStates) {
  if (!agentStates || !stageConfig.agents.length) return null;
  // Find the latest progress message from any agent in this stage
  for (const agentName of stageConfig.agents) {
    const agent = agentStates[agentName];
    if (agent?.status === 'running' && agent.progress?.length > 0) {
      const latest = agent.progress[agent.progress.length - 1];
      return latest.message;
    }
  }
  return null;
}

function ElapsedTimer() {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const start = Date.now();
    const interval = setInterval(() => {
      setElapsed(((Date.now() - start) / 1000).toFixed(1));
    }, 100);
    return () => clearInterval(interval);
  }, []);

  return (
    <span className="inline-flex items-center gap-1 text-xs text-slate-400 font-mono">
      <Clock className="h-3 w-3" />
      {elapsed}s
    </span>
  );
}

export default function PipelineStatus({ stage, agentStates }) {
  const currentIndex = stageIndex(stage);
  const isError = stage === 'error';
  const isDone = stage === 'done';
  const isActive = !isDone && !isError && currentIndex >= 0;

  // Get dynamic message from current active stage's agents
  const activeStage = STAGES[currentIndex];
  const dynamicMessage = activeStage ? getStageMessage(activeStage, agentStates) : null;

  return (
    <div className="space-y-2">
      {/* Pipeline Steps */}
      <div className="flex items-center gap-1.5 overflow-x-auto py-1">
        {STAGES.map((s, i) => {
          const Icon = s.icon;
          const active = i === currentIndex;
          const complete = currentIndex > i || isDone;
          return (
            <div key={s.key} className="flex items-center gap-1.5 flex-shrink-0">
              <motion.div
                className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium ring-1 transition-colors ${
                  isError
                    ? 'ring-rose-400/30 text-rose-300 bg-rose-500/5'
                    : complete
                    ? 'ring-emerald-400/30 text-emerald-300 bg-emerald-500/5'
                    : active
                    ? 'ring-violet-400/40 text-violet-200 bg-violet-500/10 shadow-glow'
                    : 'ring-slate-600/30 text-slate-500 bg-white/[0.02]'
                }`}
                animate={active && !isError ? { scale: [1, 1.04, 1] } : { scale: 1 }}
                transition={{ duration: 1.1, repeat: active ? Infinity : 0, ease: 'easeInOut' }}
              >
                <Icon className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">{s.label}</span>
              </motion.div>
              {i < STAGES.length - 1 && (
                <div className="h-px w-4 sm:w-6 bg-slate-600/40 relative overflow-hidden rounded-full flex-shrink-0">
                  <motion.div
                    className="absolute inset-y-0 left-0 bg-gradient-to-r from-cyan-400 to-violet-400"
                    initial={{ width: '0%' }}
                    animate={{ width: complete || active ? '100%' : '0%' }}
                    transition={{ duration: 0.4 }}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Active Stage Info */}
      <div className="flex items-center justify-between">
        {isActive && (
          <p className="text-xs text-slate-400 animate-thinking-pulse inline-flex items-center gap-1.5">
            {/* Live streaming indicator */}
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-cyan-500" />
            </span>
            <span className="text-cyan-400/80 font-medium text-[10px] uppercase tracking-wider">Live</span>
            <span className="text-slate-500">·</span>
            {dynamicMessage || STAGES[currentIndex]?.sublabel}…
          </p>
        )}
        {isDone && (
          <p className="text-xs text-emerald-400">Pipeline complete</p>
        )}
        {isError && (
          <p className="text-xs text-rose-300/80">Pipeline failed</p>
        )}
        {isActive && <ElapsedTimer />}
      </div>
    </div>
  );
}
