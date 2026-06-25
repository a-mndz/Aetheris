import { useState } from 'react';
import { motion } from 'framer-motion';
import { ChevronDown, AlertTriangle, Bot, Copy, Check, Eye, EyeOff } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import ConfidenceBadge from './ConfidenceBadge';
import BiasRiskBadge from './BiasRiskBadge';
import ReasoningPanel from './ReasoningPanel';
import PipelineStatus from './PipelineStatus';
import AgentStreamCard from './AgentStreamCard';

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for insecure contexts
      const textarea = document.createElement('textarea');
      textarea.value = text;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <button
      onClick={handleCopy}
      className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium text-slate-300 ring-1 ring-white/10 hover:bg-white/5 transition-all"
      title="Copy answer"
    >
      {copied ? (
        <>
          <Check className="h-3 w-3 text-emerald-400" />
          Copied
        </>
      ) : (
        <>
          <Copy className="h-3 w-3" />
          Copy
        </>
      )}
    </button>
  );
}

export default function MessageBubble({ message, currentStage, partialData, agentStates, isLatest }) {
  // Auto-expand reasoning for the latest assistant message
  const [reasoningOpen, setReasoningOpen] = useState(isLatest);

  if (message.role === 'user') {
    return (
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
        className="flex justify-end"
      >
        <div className="max-w-[75%] rounded-2xl rounded-tr-sm bg-gradient-to-br from-violet-600/80 to-cyan-600/60 px-4 py-2.5 text-sm text-white shadow-lg">
          {message.content}
        </div>
      </motion.div>
    );
  }

  // Check if we have partial agent outputs from the SSE stream
  const hasPartialAgents = message.status === 'pending' && partialData?.agent_outputs;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="flex gap-3"
    >
      {/* Avatar */}
      <div className="mt-1 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-cyan-500/20 to-violet-500/20 ring-1 ring-white/10">
        <Bot className="h-4 w-4 text-cyan-300" />
      </div>

      <div className="max-w-[85%] flex-1 min-w-0">
        {/* Pending State — Pipeline Progress + Live Agent Cards */}
        {message.status === 'pending' && (
          <div className="rounded-2xl glass-panel px-4 py-3 space-y-3">
            <PipelineStatus stage={currentStage} agentStates={agentStates} />

            {/* Live per-agent streaming cards */}
            {agentStates && (
              <div className="grid gap-2 sm:grid-cols-2">
                {['Breaker', 'Logician', 'Creative', 'Judge'].map((name) => (
                  <AgentStreamCard key={name} name={name} agent={agentStates[name]} />
                ))}
              </div>
            )}

            {/* Fallback: show partial agent outputs if no agentStates (legacy) */}
            {!agentStates && hasPartialAgents && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                transition={{ duration: 0.3 }}
              >
                <ReasoningPanel
                  open={true}
                  agentOutputs={partialData.agent_outputs}
                  decision={null}
                />
              </motion.div>
            )}
          </div>
        )}

        {/* Error State */}
        {message.status === 'error' && (
          <div className="rounded-2xl border border-rose-500/30 bg-rose-500/5 px-4 py-3 text-sm text-rose-200">
            <div className="flex items-center gap-2 font-medium mb-1">
              <AlertTriangle className="h-4 w-4" />
              Pipeline failed
            </div>
            <p className="text-rose-300/90">{message.error}</p>
          </div>
        )}

        {/* Done State — Answer + Reasoning */}
        {message.status === 'done' && message.response && (
          <div className="rounded-2xl glass-panel px-4 py-3.5 gradient-border">
            {/* Answer with Markdown Rendering */}
            <div className="prose-aetheris text-[0.95rem] text-slate-100">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.response.answer || ''}
              </ReactMarkdown>
            </div>

            {/* Metadata Bar */}
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <ConfidenceBadge score={message.response.confidence_score} />
              <BiasRiskBadge risk={message.response.bias_risk} />

              <div className="ml-auto flex items-center gap-1.5">
                <CopyButton text={message.response.answer || ''} />

                <button
                  onClick={() => setReasoningOpen((v) => !v)}
                  className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium text-slate-300 ring-1 ring-white/10 hover:bg-white/5 transition-all"
                >
                  {reasoningOpen ? (
                    <>
                      <EyeOff className="h-3 w-3" />
                      Hide reasoning
                    </>
                  ) : (
                    <>
                      <Eye className="h-3 w-3" />
                      View reasoning
                    </>
                  )}
                  <ChevronDown
                    className={`h-3 w-3 transition-transform duration-200 ${reasoningOpen ? 'rotate-180' : ''}`}
                  />
                </button>
              </div>
            </div>

            {/* Expandable Reasoning Panel */}
            <ReasoningPanel
              open={reasoningOpen}
              agentOutputs={message.response.agent_outputs}
              decision={message.response.decision}
            />
          </div>
        )}
      </div>
    </motion.div>
  );
}
