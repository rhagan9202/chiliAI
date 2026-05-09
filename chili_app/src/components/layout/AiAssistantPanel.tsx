import { Bot, SendHorizontal } from 'lucide-react'

export function AiAssistantPanel() {
  return (
    <aside className="ai-panel" aria-label="AI investigator assistant">
      <div className="ai-panel__header">
        <div className="ai-panel__icon" aria-hidden="true">
          <Bot size={16} />
        </div>
        <div>
          <div className="ai-panel__title">AI Investigator</div>
          <div className="ai-panel__subtitle">Triage support, not a final decision</div>
        </div>
      </div>
      <div className="ai-panel__body">
        <p>
          The production RAG assistant will attach entity, alert, case, and evidence context
          as backend chat endpoints come online.
        </p>
      </div>
      <form className="ai-panel__composer">
        <input aria-label="Ask the AI investigator" placeholder="Ask about this workspace..." />
        <button aria-label="Send message" type="button">
          <SendHorizontal size={15} />
        </button>
      </form>
    </aside>
  )
}