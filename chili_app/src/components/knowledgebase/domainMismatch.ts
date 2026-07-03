/**
 * True when a knowledge base was stamped with a creating domain that differs
 * from the currently active one. A missing (`null`/`undefined`) KB domain is a
 * legacy KB created before domain stamping and is never treated as a mismatch.
 */
export function isDomainMismatch(
  kbDomain: string | null | undefined,
  activeDomainName: string | null | undefined,
): boolean {
  return Boolean(kbDomain) && Boolean(activeDomainName) && kbDomain !== activeDomainName
}
