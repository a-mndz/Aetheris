import { useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import MessageBubble from './MessageBubble';
import EmptyState from './EmptyState';
import { messageVariants } from '../utils/animations';
import { useSettingsStore } from '../store/useSettingsStore';

export default function ChatWindow({ messages, currentStage, agentStates, partialData, onSuggestion }) {
  const bottomRef = useRef(null);
  const lastMessage = messages[messages.length - 1];
  const animationsEnabled = useSettingsStore((state) => state.animationsEnabled);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages.length, lastMessage?.status, currentStage]);

  if (messages.length === 0) {
    return <EmptyState onSuggestion={onSuggestion} />;
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 md:px-8">
      <div className="mx-auto flex max-w-3xl flex-col gap-5">
        {messages.map((m, i) => (
          <motion.div
            key={m.id}
            initial={animationsEnabled ? 'hidden' : false}
            animate={animationsEnabled ? 'visible' : false}
            variants={messageVariants}
          >
            <MessageBubble
              message={m}
              currentStage={currentStage}
              agentStates={agentStates}
              partialData={partialData}
              isLatest={i === messages.length - 1 || i === messages.length - 2}
            />
          </motion.div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
