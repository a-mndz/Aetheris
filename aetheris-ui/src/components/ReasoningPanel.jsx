import { motion, AnimatePresence } from 'framer-motion';
import { Brain, Palette, Scale, Shield } from 'lucide-react';
import AgentThinkingCard from './AgentThinkingCard';
import JudgePanel from './JudgePanel';

export default function ReasoningPanel({ open, agentOutputs, decision }) {
  return (
    <AnimatePresence initial={false}>
      {open && (
        <motion.div
          key="reasoning"
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.3, ease: 'easeInOut' }}
          className="overflow-hidden"
        >
          <div className="mt-4 space-y-3">
            {/* Section Header */}
            <div className="flex items-center gap-2 px-1">
              <div className="h-px flex-1 bg-gradient-to-r from-transparent via-white/10 to-transparent" />
              <span className="text-[10px] uppercase tracking-widest text-slate-500 font-medium">
                Multi-Agent Reasoning
              </span>
              <div className="h-px flex-1 bg-gradient-to-r from-transparent via-white/10 to-transparent" />
            </div>

            {/* Agent Cards Grid */}
            <div className="grid gap-3 md:grid-cols-2">
              <AgentThinkingCard
                icon={Brain}
                title="Logician Agent"
                accentClass="agent-card-logician"
                dotClass="timeline-step-cyan"
                agent={agentOutputs?.logician}
                defaultExpanded={true}
              />
              <AgentThinkingCard
                icon={Palette}
                title="Creative Agent"
                accentClass="agent-card-creative"
                dotClass="timeline-step-violet"
                agent={agentOutputs?.creative}
                defaultExpanded={true}
              />
            </div>

            {/* Judge Panel */}
            <JudgePanel decision={decision} agentOutputs={agentOutputs} />
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
