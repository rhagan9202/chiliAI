import { PagePlaceholder } from './PagePlaceholder'
import './pages.css'

export function KnowledgeBaseManagerPage() {
  return (
    <PagePlaceholder eyebrow="Ingestion control" title="Knowledge Base Manager">
      <p>
        Knowledge base management will expose document upload, document inventory,
        ingestion status, and index rebuild controls backed by the FastAPI gateway.
      </p>
    </PagePlaceholder>
  )
}