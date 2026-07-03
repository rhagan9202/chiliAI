import type { ConfigSwapResponse } from '../../api/contracts'
import './configManager.css'

export function SwapResultBanner({ result }: { result: ConfigSwapResponse }) {
  return (
    <div className="config-manager__swap-result" data-testid="swap-result" role="status">
      <p>
        {result.reason === 'switch' ? 'Switched to' : 'Applied'}{' '}
        <strong>{result.pack_name}</strong>
        {result.previous_pack_name && result.previous_pack_name !== result.pack_name ? (
          <> (was {result.previous_pack_name})</>
        ) : null}{' '}
        — generation {result.generation}. The workspace reloaded the new domain in place.
      </p>
      {result.rag_degraded_to_fallback ? (
        <p className="config-manager__warning" role="alert">
          RAG composition for the new pack failed; the API degraded to the fallback pipeline.
        </p>
      ) : null}
      {!result.event_published ? (
        <p className="config-manager__warning" role="alert">
          The config.updated event could not be published — the worker may still be serving the
          previous pack.
        </p>
      ) : null}
    </div>
  )
}
