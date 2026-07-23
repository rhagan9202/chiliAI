import type { PolicyItemSummaryResponse } from '../../api/contracts'

export function policyItemsForTarget(
  items: PolicyItemSummaryResponse[],
  targetKind: 'entity' | 'alert',
  targetRef: string,
): PolicyItemSummaryResponse[] {
  return items.filter(
    (item) => item.target_kind === targetKind && item.target_ref === targetRef,
  )
}
