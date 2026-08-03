/**
 * Explanation review persistence (SAFE-CMS-010). An analyst challenges an
 * evidence narrative, then sees that status survive case/workbench navigation.
 */
import { expect, test } from '@playwright/test'

import { seeded } from './helpers/seeded'

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000'

test.describe('Explanation reviews', () => {
  test('persists a challenged narrative across case dossier and cockpit navigation', async ({
    page,
    request,
  }) => {
    const {
      alert_id: alert,
      entity_id: entity,
      evidence_pack_id: evidence,
      knowledge_base_id: kb,
    } = seeded()
    const created = await request.post(
      `${API}/cases?knowledge_base_id=${encodeURIComponent(kb)}`,
      {
        data: {
          alert_ids: [alert],
          priority: 'high',
          title: 'Explanation review persistence case',
        },
      },
    )
    expect(created.ok(), `case create failed with ${created.status()}`).toBe(true)
    const { case: createdCase } = (await created.json()) as { case: { id: string } }
    const caseId = createdCase.id
    const workbenchUrl = `/investigation/${entity}?kb=${kb}&alert=${alert}&case=${caseId}&evidence=${evidence}`

    await page.goto(workbenchUrl)
    await page.getByRole('button', { name: 'View cockpit evidence' }).click()
    await expect(page.getByTestId('evidence-pack-viewer')).toBeVisible()

    const review = page.getByRole('group', { name: 'Narrative review' })
    await review.getByLabel('Narrative review state').selectOption('unsupported')
    await review.getByLabel('Narrative review reason').selectOption('missing_source')
    await review.getByLabel('Narrative review comment').fill('Needs source confirmation before referral.')
    const reviewResponse = page.waitForResponse(
      (response) =>
        response.url().includes(`/evidence-packs/${evidence}/reviews`)
        && response.request().method() === 'POST',
    )
    await review.getByRole('button', { name: 'Save narrative review' }).click()
    await expect((await reviewResponse).ok()).toBe(true)
    await expect(review).toContainText('Unsupported')

    await page.goto(`/cases?kb=${kb}&case=${caseId}`)
    const dossier = page.getByRole('region', { name: 'Case dossier' })
    await expect(dossier.getByText('Explanation reviews', { exact: true })).toBeVisible()
    await expect(dossier.getByText(evidence).first()).toBeVisible()
    await expect(dossier.getByText('narrative:narrative')).toBeVisible()
    await expect(dossier.getByText('unsupported')).toBeVisible()

    await page.goto(workbenchUrl)
    await page.getByRole('button', { name: 'View cockpit evidence' }).click()
    await expect(page.getByRole('group', { name: 'Narrative review' })).toContainText('Unsupported')
  })
})
