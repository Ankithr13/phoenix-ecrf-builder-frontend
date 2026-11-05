/* Small display helpers shared by more than one page. */

/* A cost the server could not work out because prices are not configured
   comes back as null. It is never shown as $0. */
export function costText(usd: number | null | undefined): string {
  return typeof usd === "number" ? `$${usd.toFixed(4)}` : "cost not configured";
}
