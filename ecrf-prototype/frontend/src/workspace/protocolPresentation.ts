import type { ProtocolListItem } from "../api/types";

export type ProtocolStage = "not_extracted" | "draft" | "locked";
export type ProtocolFilter = "all" | ProtocolStage;

export const PROTOCOL_FILTERS: { value: ProtocolFilter; label: string }[] = [
  { value: "all", label: "All protocols" },
  { value: "draft", label: "Needs review" },
  { value: "not_extracted", label: "Needs extraction" },
  { value: "locked", label: "Locked templates" },
];

export const PROTOCOL_STAGE_LABELS: Record<ProtocolStage, string> = {
  not_extracted: "Needs extraction",
  draft: "Review / finalization pending",
  locked: "Template locked",
};

export function protocolStage(protocol: ProtocolListItem): ProtocolStage {
  return protocol.latest_version === null ? "not_extracted" : protocol.state === "locked" ? "locked" : "draft";
}

export function protocolFilter(value: string | null): ProtocolFilter {
  if (value === "needs_review") return "draft";
  return PROTOCOL_FILTERS.find((filter) => filter.value === value)?.value ?? "all";
}

export function matchesProtocol(protocol: ProtocolListItem, filter: ProtocolFilter, search: string): boolean {
  return (filter === "all" || protocolStage(protocol) === filter)
    && `${protocol.name} ${protocol.filename}`.toLowerCase().includes(search.trim().toLowerCase());
}

export function nextProtocolAction(protocol: ProtocolListItem, can: (permission: string) => boolean) {
  const stage = protocolStage(protocol);
  if (stage === "not_extracted" && can("protocol.extract")) {
    return { to: `/sponsor/p/${protocol.id}/visits`, label: protocol.plan?.visits.length ? "Continue extraction" : "Extract forms" };
  }
  return {
    to: `/sponsor/p/${protocol.id}/review`,
    label: stage === "not_extracted" ? "View protocol" : stage === "locked" ? "View locked form" : can("form.edit") ? "Continue review" : can("protocol.lock") ? "Review template" : "View draft",
  };
}

export function protocolUploadDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Date unavailable" : date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}
