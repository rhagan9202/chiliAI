import { ChatContainer } from '../components/chat/ChatContainer'
import { useSessionConversationId } from '../hooks/useSessionConversationId'

export function RagChat(): React.ReactElement {
  const conversationId = useSessionConversationId()
  return (
    <section
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        height: '100%',
        minHeight: 540,
      }}
    >
      <header>
        <h1>RAG Chat</h1>
        <p style={{ marginTop: 0 }}>
          Ask questions and receive answers grounded in the selected
          knowledge base. Citations link to the Investigation Workbench.
        </p>
      </header>
      <ChatContainer conversationId={conversationId} />
    </section>
  )
}

export default RagChat
