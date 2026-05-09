import { PagePlaceholder } from './PagePlaceholder'
import './pages.css'

export function RagChatPage() {
  return (
    <PagePlaceholder eyebrow="Conversational RAG" title="RAG Chat">
      <p>
        RAG chat will provide conversation history, message streaming, citations, and contextual
        attachments from selected alerts, entities, cases, and evidence packs.
      </p>
    </PagePlaceholder>
  )
}