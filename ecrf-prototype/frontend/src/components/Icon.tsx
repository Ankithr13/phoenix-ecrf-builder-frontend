const PATHS = {
  dashboard: "M3 3h7v7H3ZM14 3h7v4h-7ZM14 11h7v10h-7ZM3 14h7v7H3Z",
  upload: "M12 16V3M7 8l5-5 5 5M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5",
  chevron: "M9 5l7 7-7 7",
  protocols: "M9 5H6a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-3M9 3h6v4H9zM8 12h8M8 17h5",
  queries: "M21 11a8 8 0 0 1-8 8H7l-5 3V11a8 8 0 0 1 8-8h3a8 8 0 0 1 8 8ZM7 9h9M7 13h6",
  visits: "M8 2v4M16 2v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2ZM8 14h2M14 14h2M8 18h2",
  forms: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8ZM14 2v6h6M8 12h8M8 16h8",
  sites: "M3 21h18M5 21V7l7-4 7 4v14M9 21v-5h6v5M9 8h1M14 8h1M9 12h1M14 12h1",
  data: "M14 2H6a2 2 0 0 0-2 2v5M4 19v1a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8ZM14 2v6h6M2 14h10M8 10l4 4-4 4",
  reports: "M3 3v18h18M8 16v-5M13 16V6M18 16v-8",
  patients: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75",
  signOut: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
  menu: "M4 6h16M4 12h16M4 18h16",
  close: "M6 6l12 12M6 18 18 6",
  search: "M10.5 3a7.5 7.5 0 1 0 0 15 7.5 7.5 0 0 0 0-15ZM16 16l5 5",
  refresh: "M20 7v5h-5M4 17v-5h5M6.1 6a8 8 0 0 1 13.1 3M4.8 15A8 8 0 0 0 18 18",
};

export type IconName = keyof typeof PATHS;

export default function Icon({ name, className = "sidebar-icon" }: { name: IconName; className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name]} />
    </svg>
  );
}
