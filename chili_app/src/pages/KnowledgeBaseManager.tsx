import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Skeleton } from '../components/common/Skeleton'
import { showToast } from '../components/common/toastStore'
import { CreateKbForm } from '../components/knowledgebase/CreateKbForm'
import { KbTable } from '../components/knowledgebase/KbTable'
import { useKnowledgeBases } from '../hooks/useKnowledgeBases'

export function KnowledgeBaseManager(): React.ReactElement {
  const [createOpen, setCreateOpen] = useState(false)
  const navigate = useNavigate()
  const { data, isLoading, error } = useKnowledgeBases()

  useEffect(() => {
    if (error) {
      showToast('error', `Failed to load knowledge bases: ${error.message}`)
    }
  }, [error])

  return (
    <section>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 16,
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        <h1 style={{ margin: 0 }}>Knowledge Base Manager</h1>
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          style={{
            padding: '8px 14px',
            borderRadius: 4,
            border: 'none',
            background: 'var(--accent, #aa3bff)',
            color: '#fff',
            cursor: 'pointer',
            fontSize: 14,
            fontWeight: 500,
          }}
        >
          + Create Knowledge Base
        </button>
      </div>

      {isLoading ? (
        <Skeleton width="100%" height={160} />
      ) : error ? (
        <p style={{ color: '#b91c1c' }}>
          Failed to load knowledge bases: {error.message}
        </p>
      ) : (
        <KbTable
          knowledgeBases={data?.items ?? []}
          onSelect={(kb) => navigate(`/knowledgebases/${kb.id}`)}
        />
      )}

      <CreateKbForm
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(id) => navigate(`/knowledgebases/${id}`)}
      />
    </section>
  )
}

export default KnowledgeBaseManager
