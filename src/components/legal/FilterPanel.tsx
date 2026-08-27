import { useState } from "react";
import { Search, ChevronDown, ChevronUp } from "lucide-react";
import { FILTER_ISSUES, OUTCOME_FILTERS, type Precedent } from "@/data/precedents";
import { HIGH_COURTS, expandSection } from "@/lib/legal-taxonomy";

export interface Filters {
  courts: string[];
  dateFrom: string | null;
  dateTo: string | null;
  sectionQuery: string;
  matchEquivalents: boolean;
  issues: string[];
  outcomes: string[];
}

export const DEFAULT_FILTERS: Filters = {
  courts: [],
  dateFrom: null,
  dateTo: null,
  sectionQuery: "",
  matchEquivalents: true,
  issues: [],
  outcomes: [],
};

export function computeFacets(results: Precedent[]) {
  const counts = {
    courts: {} as Record<string, number>,
    years: {} as Record<string, number>,
    issues: {} as Record<string, number>,
    outcomes: {} as Record<string, number>,
  };

  results.forEach((r) => {
    counts.courts[r.court] = (counts.courts[r.court] || 0) + 1;
    counts.outcomes[r.outcome] = (counts.outcomes[r.outcome] || 0) + 1;
    r.filterIssues.forEach((issue) => {
      counts.issues[issue] = (counts.issues[issue] || 0) + 1;
    });
  });

  return counts;
}

interface FilterPanelProps {
  filters: Filters;
  onChange: (filters: Filters) => void;
  onReset: () => void;
  counts: ReturnType<typeof computeFacets>;
}

function Group({
  legend,
  options,
  selected,
  counts,
  onToggle,
}: {
  legend: string;
  options: string[];
  selected: string[];
  counts: Record<string, number>;
  onToggle: (option: string) => void;
}) {
  const [isOpen, setIsOpen] = useState(true);

  return (
    <fieldset className="mt-6 first:mt-0">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between text-left focus:outline-none"
      >
        <legend className="text-[12px] font-semibold tracking-wide text-navy uppercase">
          {legend}
        </legend>
        {isOpen ? (
          <ChevronUp className="size-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="size-4 text-muted-foreground" />
        )}
      </button>

      {isOpen && (
        <div className="mt-2.5 space-y-1.5">
          {options.map((option) => {
            const count = counts[option] || 0;
            return (
              <label
                key={option}
                className="flex cursor-pointer items-start gap-2 text-[13px] text-foreground"
              >
                <input
                  type="checkbox"
                  checked={selected.includes(option)}
                  onChange={() => onToggle(option)}
                  className="mt-0.5 size-3.5 rounded-sm accent-[var(--brand-blue)]"
                />
                <span className="flex-1">
                  {option} <span className="text-muted-foreground">({count})</span>
                </span>
              </label>
            );
          })}
        </div>
      )}
    </fieldset>
  );
}

function CourtFilter({
  selected,
  counts,
  onChange,
}: {
  selected: string[];
  counts: Record<string, number>;
  onChange: (courts: string[]) => void;
}) {
  const [isOpen, setIsOpen] = useState(true);
  const [search, setSearch] = useState("");

  const toggleCourt = (courtName: string, subBenches: string[] = []) => {
    const isSelected = selected.includes(courtName);
    const related = [courtName, ...subBenches];

    if (isSelected) {
      // Unselect court and its benches
      onChange(selected.filter((c) => !related.includes(c)));
    } else {
      // Select court and its benches
      const newSelected = [...selected];
      related.forEach((c) => {
        if (!newSelected.includes(c)) newSelected.push(c);
      });
      onChange(newSelected);
    }
  };

  const toggleBench = (benchName: string) => {
    if (selected.includes(benchName)) {
      onChange(selected.filter((c) => c !== benchName));
    } else {
      onChange([...selected, benchName]);
    }
  };

  const term = search.toLowerCase();

  // Always show Supreme Court if it matches
  const scName = "Supreme Court of India";
  const showSc = scName.toLowerCase().includes(term);

  // Filter high courts
  const filteredHighCourts = HIGH_COURTS.map((hc) => {
    const matchesHc = hc.name.toLowerCase().includes(term);
    const matchedBenches = hc.benches?.filter((b) => b.toLowerCase().includes(term)) || [];
    if (matchesHc || matchedBenches.length > 0) {
      return {
        ...hc,
        // If HC matches, show all its benches. If only benches match, show only those benches.
        benches: matchesHc ? hc.benches : matchedBenches,
        matchesHc,
      };
    }
    return null;
  }).filter(Boolean);

  return (
    <fieldset className="mt-6 first:mt-0">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between text-left focus:outline-none"
      >
        <legend className="text-[12px] font-semibold tracking-wide text-navy uppercase">
          Court level
        </legend>
        {isOpen ? (
          <ChevronUp className="size-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="size-4 text-muted-foreground" />
        )}
      </button>

      {isOpen && (
        <div className="mt-2.5">
          <div className="relative mb-3">
            <Search className="absolute left-2 top-1.5 size-3.5 text-muted-foreground" />
            <input
              type="text"
              placeholder="Filter courts..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-md border border-border bg-background py-1.5 pl-7 pr-2 text-[12.5px] text-foreground focus:outline-none focus:ring-2 focus:ring-brand-blue"
            />
          </div>

          <div className="space-y-1.5 max-h-60 overflow-y-auto pr-1">
            {showSc && (
              <label className="flex cursor-pointer items-start gap-2 text-[13px] text-foreground font-medium pb-2 border-b border-border/50">
                <input
                  type="checkbox"
                  checked={selected.includes(scName)}
                  onChange={() => toggleBench(scName)}
                  className="mt-0.5 size-3.5 rounded-sm accent-[var(--brand-blue)]"
                />
                <span className="flex-1">
                  {scName}{" "}
                  <span className="text-muted-foreground font-normal">({counts[scName] || 0})</span>
                </span>
              </label>
            )}

            {filteredHighCourts.map((hc) => {
              if (!hc) return null;
              const hcCount = counts[hc.name] || 0;
              const hasBenches = hc.benches && hc.benches.length > 0;
              const isHcSelected = selected.includes(hc.name);

              return (
                <div key={hc.id} className="pt-1">
                  <label className="flex cursor-pointer items-start gap-2 text-[13px] text-foreground">
                    <input
                      type="checkbox"
                      checked={isHcSelected}
                      onChange={() => toggleCourt(hc.name, hc.benches || [])}
                      className="mt-0.5 size-3.5 rounded-sm accent-[var(--brand-blue)]"
                    />
                    <span className="flex-1">
                      {hc.name} <span className="text-muted-foreground">({hcCount})</span>
                    </span>
                  </label>

                  {hasBenches && (
                    <div className="ml-2 mt-1 border-l-2 border-border/60 pl-3 space-y-1">
                      {hc.benches!.map((bench) => {
                        const benchCount = counts[bench] || 0;
                        return (
                          <label
                            key={bench}
                            className="flex cursor-pointer items-start gap-2 text-[12px] text-muted-foreground hover:text-foreground transition-colors"
                          >
                            <input
                              type="checkbox"
                              checked={selected.includes(bench)}
                              onChange={() => toggleBench(bench)}
                              className="mt-0.5 size-3 rounded-sm accent-[var(--brand-blue)]"
                            />
                            <span className="flex-1">
                              {bench} <span>({benchCount})</span>
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </fieldset>
  );
}

function DateRangeFilter({
  dateFrom,
  dateTo,
  onChange,
}: {
  dateFrom: string | null;
  dateTo: string | null;
  onChange: (from: string | null, to: string | null) => void;
}) {
  const [isOpen, setIsOpen] = useState(true);

  const applyPreset = (years: number | null) => {
    if (years === null) {
      onChange(null, null);
      return;
    }
    const end = new Date();
    const start = new Date();
    start.setFullYear(start.getFullYear() - years);

    // Format to YYYY-MM-DD
    const formatDate = (d: Date) => d.toISOString().split("T")[0] || null;
    onChange(formatDate(start), formatDate(end));
  };

  return (
    <fieldset className="mt-6 first:mt-0">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between text-left focus:outline-none"
      >
        <legend className="text-[12px] font-semibold tracking-wide text-navy uppercase">
          Date range
        </legend>
        {isOpen ? (
          <ChevronUp className="size-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="size-4 text-muted-foreground" />
        )}
      </button>

      {isOpen && (
        <div className="mt-2.5">
          <div className="flex flex-wrap gap-2 mb-3">
            {[
              { label: "1 yr", years: 1 },
              { label: "3 yrs", years: 3 },
              { label: "5 yrs", years: 5 },
              { label: "All", years: null },
            ].map((preset) => (
              <button
                key={preset.label}
                type="button"
                onClick={() => applyPreset(preset.years)}
                className="rounded-full border border-border bg-background px-2.5 py-1 text-[11.5px] font-medium text-navy hover:bg-accent transition-colors"
              >
                {preset.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <input
              type="date"
              value={dateFrom || ""}
              onChange={(e) => onChange(e.target.value || null, dateTo)}
              className="w-full rounded-md border border-border bg-background px-2 py-1 text-[12.5px] text-foreground focus:outline-none focus:ring-2 focus:ring-brand-blue"
            />
            <span className="text-[12px] text-muted-foreground">to</span>
            <input
              type="date"
              value={dateTo || ""}
              onChange={(e) => onChange(dateFrom, e.target.value || null)}
              className="w-full rounded-md border border-border bg-background px-2 py-1 text-[12.5px] text-foreground focus:outline-none focus:ring-2 focus:ring-brand-blue"
            />
          </div>
        </div>
      )}
    </fieldset>
  );
}

function ActSectionFilter({
  sectionQuery,
  matchEquivalents,
  onChangeQuery,
  onChangeMatch,
}: {
  sectionQuery: string;
  matchEquivalents: boolean;
  onChangeQuery: (q: string) => void;
  onChangeMatch: (m: boolean) => void;
}) {
  const [isOpen, setIsOpen] = useState(true);

  return (
    <fieldset className="mt-6 first:mt-0">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between text-left focus:outline-none"
      >
        <legend className="text-[12px] font-semibold tracking-wide text-navy uppercase">
          Act and section
        </legend>
        {isOpen ? (
          <ChevronUp className="size-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="size-4 text-muted-foreground" />
        )}
      </button>

      {isOpen && (
        <div className="mt-2.5 space-y-3">
          <input
            type="text"
            placeholder="e.g. 482 or 138"
            value={sectionQuery}
            onChange={(e) => onChangeQuery(e.target.value)}
            className="w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-[12.5px] text-foreground focus:outline-none focus:ring-2 focus:ring-brand-blue"
          />
          <label className="flex cursor-pointer items-start gap-2 text-[12.5px] text-muted-foreground hover:text-foreground transition-colors">
            <input
              type="checkbox"
              checked={matchEquivalents}
              onChange={(e) => onChangeMatch(e.target.checked)}
              className="mt-0.5 size-3.5 rounded-sm accent-[var(--brand-blue)]"
            />
            <span className="flex-1">Match new BNSS/BNS equivalents</span>
          </label>
        </div>
      )}
    </fieldset>
  );
}

export function FilterPanel({ filters, onChange, onReset, counts }: FilterPanelProps) {
  const toggleArrayOption = (group: "courts" | "issues" | "outcomes", option: string) => {
    const current = filters[group] as string[];
    const updated = current.includes(option)
      ? current.filter((val) => val !== option)
      : [...current, option];
    onChange({ ...filters, [group]: updated });
  };

  return (
    <div className="rounded-md border border-border bg-surface p-4 shadow-subtle">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-serif text-[16px] font-semibold text-navy">Refine Results</h2>
        <button
          type="button"
          onClick={onReset}
          className="rounded-md border border-border px-2.5 py-1 text-[12px] text-navy hover:bg-accent"
        >
          Reset filters
        </button>
      </div>

      <CourtFilter
        selected={filters.courts}
        counts={counts.courts}
        onChange={(courts) => onChange({ ...filters, courts })}
      />
      <ActSectionFilter
        sectionQuery={filters.sectionQuery}
        matchEquivalents={filters.matchEquivalents}
        onChangeQuery={(q) => onChange({ ...filters, sectionQuery: q })}
        onChangeMatch={(m) => onChange({ ...filters, matchEquivalents: m })}
      />
      <DateRangeFilter
        dateFrom={filters.dateFrom}
        dateTo={filters.dateTo}
        onChange={(from, to) => onChange({ ...filters, dateFrom: from, dateTo: to })}
      />
      <Group
        legend="Requested outcome"
        options={[...OUTCOME_FILTERS]}
        selected={filters.outcomes}
        counts={counts.outcomes}
        onToggle={(outcome) => toggleArrayOption("outcomes", outcome)}
      />
      <Group
        legend="Legal issue"
        options={[...FILTER_ISSUES]}
        selected={filters.issues}
        counts={counts.issues}
        onToggle={(issue) => toggleArrayOption("issues", issue)}
      />
    </div>
  );
}
