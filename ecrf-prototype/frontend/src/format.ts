/* Small display helpers shared by more than one page. */

import type { Role } from "./api/types";

export const ROLE_LABEL: Record<Role, string> = {
  admin: "Admin", builder: "Database builder", data_manager: "Data manager", monitor: "Monitor",
  read_only: "Read only", investigator: "Investigator", site_coordinator: "Site coordinator",
  site_data_entry: "Site data entry",
};

/* A cost the server could not work out because prices are not configured
   comes back as null. It is never shown as $0. */
export function costText(usd: number | null | undefined): string {
  return typeof usd === "number" ? `$${usd.toFixed(4)}` : "cost not configured";
}
