import { useState } from 'react'

import { useConfigPacks, useDomainConfig, useSwitchPack } from '../../api/config'
import type { ConfigSwapResponse, PackSummary } from '../../api/contracts'
import { Card } from '../ui/Card'
import { ErrorState } from '../ui/ErrorState'
import { LoadingState } from '../ui/LoadingState'
import { SwapResultBanner } from './SwapResultBanner'
import { TransportWarning } from './TransportWarning'
import './configManager.css'

function errorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return 'The pack switch failed.'
}

export function PackSwitcher() {
  const packsQuery = useConfigPacks()
  // The active side of the transport comparison; already resolved by the API.
  const domainConfig = useDomainConfig()
  const switchMutation = useSwitchPack()
  const [pendingPack, setPendingPack] = useState<PackSummary | null>(null)
  const [lastSwap, setLastSwap] = useState<ConfigSwapResponse | null>(null)

  if (packsQuery.isLoading) {
    return <LoadingState label="Loading domain packs" />
  }

  if (packsQuery.isError || !packsQuery.data) {
    return <ErrorState description="Domain packs could not be loaded. Switching packs requires the administrator role." />
  }

  const { packs, active, generation } = packsQuery.data

  const confirmSwitch = (pack: PackSummary) => {
    switchMutation.mutate(
      { pack: pack.name },
      {
        onSuccess: (result) => {
          setLastSwap(result)
          setPendingPack(null)
        },
      },
    )
  }

  return (
    <Card>
      <div className="pack-switcher" data-testid="pack-switcher">
        <div className="pack-switcher__meta">
          <span>
            Active pack source: <strong>{active.source}</strong>
            {active.pack_name ? (
              <>
                {' '}
                (<strong>{active.pack_name}</strong>)
              </>
            ) : null}
          </span>
          <span>
            Config generation: <strong data-testid="config-generation">{generation}</strong>
          </span>
        </div>
        <ul className="pack-switcher__list">
          {packs.map((pack) => (
            <li
              className={
                pack.active
                  ? 'pack-switcher__item pack-switcher__item--active'
                  : 'pack-switcher__item'
              }
              data-testid={`pack-item-${pack.name}`}
              key={pack.path}
            >
              <div className="pack-switcher__item-main">
                <span className="pack-switcher__item-name">
                  {pack.display_name ?? pack.name}
                </span>
                <span className="pack-switcher__item-file">{pack.file_name}</span>
                {pack.active ? (
                  <span className="pack-switcher__badge pack-switcher__badge--active">Active</span>
                ) : null}
                {!pack.valid ? (
                  <span className="pack-switcher__badge pack-switcher__badge--invalid">Invalid</span>
                ) : null}
              </div>
              {!pack.valid && pack.error ? (
                <p className="pack-switcher__item-error" role="note">
                  {pack.error}
                </p>
              ) : null}
              {!pack.active ? (
                <div className="pack-switcher__item-actions">
                  {pendingPack?.path === pack.path ? (
                    <>
                      <span className="pack-switcher__confirm-copy">
                        Switch the whole workspace to “{pack.display_name ?? pack.name}”?
                      </span>
                      {/* Above Confirm, so it is read before the irreversible
                          click rather than explained afterwards (UXA-404). */}
                      <TransportWarning
                        active={domainConfig.data?.events}
                        candidate={pack.transport}
                      />
                      <button
                        className="page-button"
                        disabled={switchMutation.isPending}
                        onClick={() => confirmSwitch(pack)}
                        type="button"
                      >
                        {switchMutation.isPending ? 'Switching…' : 'Confirm switch'}
                      </button>
                      <button
                        className="page-button page-button--secondary"
                        disabled={switchMutation.isPending}
                        onClick={() => setPendingPack(null)}
                        type="button"
                      >
                        Cancel
                      </button>
                    </>
                  ) : (
                    <button
                      className="page-button page-button--secondary"
                      disabled={!pack.valid || switchMutation.isPending}
                      onClick={() => {
                        switchMutation.reset()
                        setLastSwap(null)
                        setPendingPack(pack)
                      }}
                      type="button"
                    >
                      Activate
                    </button>
                  )}
                </div>
              ) : null}
            </li>
          ))}
        </ul>
        {packs.length === 0 ? (
          <p className="pack-switcher__empty">No domain packs found in the allowed config directories.</p>
        ) : null}
        {switchMutation.isError ? (
          <p className="config-manager__error" role="alert">
            {errorMessage(switchMutation.error)}
          </p>
        ) : null}
        {lastSwap ? <SwapResultBanner result={lastSwap} /> : null}
      </div>
    </Card>
  )
}
