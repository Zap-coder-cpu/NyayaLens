import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState, useMemo } from "react";
import {
  SlidersHorizontal,
  ArrowLeft,
  X,
  AlignJustify,
  LayoutList,
  Search,
  Network,
} from "lucide-react";
import { Navbar } from "@/components/legal/Navbar";
import { SiteFooter } from "@/components/legal/SiteFooter";
import { SearchPanel } from "@/components/legal/SearchPanel";
import {
  FilterPanel,
  DEFAULT_FILTERS,
  computeFacets,
  type Filters,
} from "@/components/legal/FilterPanel";
import { PrecedentItem } from "@/components/legal/PrecedentItem";
import { ResultSkeleton } from "@/components/legal/ResultSkeleton";
import { CaseGraph } from "@/components/legal/CaseGraph";
import {
  COURTS,
  DEFAULT_QUERY,
  FILTER_ISSUES,
  OUTCOME_FILTERS,
  type LegalCategory,
  type Precedent,
} from "@/data/precedents";
import { searchCasesFn } from "@/api/search";
import { caseGraphFn } from "@/api/graph";
import type { SearchEngineResponse } from "@/contracts/search";
import type { CaseGraphResponse } from "@/contracts/graph";
import { expandSection } from "@/lib/legal-taxonomy";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Nyayalens — Source-Linked Hybrid Precedent Retrieval" },
      {
        name: "description",
        content:
          "Search an imported Supreme Court and High Court judgment corpus using local dense and exact legal-term retrieval.",
      },
      { property: "og:title", content: "Nyayalens — Precedent Retrieval Engine" },
      {
        property: "og:description",
        content:
          "Retrieve matching precedents from imported judgments with exact evidence and transparent ranking traces.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

function Index() {
  const [query, setQuery] = useState(DEFAULT_QUERY);
  const [hasSearched, setHasSearched] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [activeCategory, setActiveCategory] = useState<LegalCategory>("All");
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [results, setResults] = useState<Precedent[]>([]);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchMeta, setSearchMeta] = useState<Omit<SearchEngineResponse, "results"> | null>(null);
  const [sortOrder, setSortOrder] = useState("relevance");
  const [isCompact, setIsCompact] = useState(false);
  const [resultsQuery, setResultsQuery] = useState("");
  const [graphView, setGraphView] = useState(false);
  const [graphData, setGraphData] = useState<CaseGraphResponse | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphError, setGraphError] = useState<string | null>(null);
  const latestRequestId = useRef(0);
  const graphRunIdRef = useRef<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const savedQuery = params.get("case-description");
    const savedCourts = params.getAll("court");
    const savedDateFrom = params.get("dateFrom");
    const savedDateTo = params.get("dateTo");
    const savedSectionQuery = params.get("sectionQuery") || "";
    const savedMatchEquivalents = params.get("matchEquivalents") !== "false";
    const savedIssues = params.getAll("issue");
    const savedOutcomes = params.getAll("outcome");
    if (savedQuery) setQuery(savedQuery);
    setFilters((current) => ({
      ...current,
      courts: savedCourts.filter((c) => (COURTS as readonly string[]).includes(c)),
      dateFrom: savedDateFrom,
      dateTo: savedDateTo,
      sectionQuery: savedSectionQuery,
      matchEquivalents: savedMatchEquivalents,
      issues: savedIssues.filter((i) => (FILTER_ISSUES as readonly string[]).includes(i)),
      outcomes: savedOutcomes.filter((o) => (OUTCOME_FILTERS as readonly string[]).includes(o)),
    }));
  }, []);

  useEffect(() => {
    if (!graphView || results.length === 0) return;
    if (graphRunIdRef.current === searchMeta?.runId) return;
    let cancelled = false;
    setGraphLoading(true);
    setGraphError(null);
    caseGraphFn({ data: { caseIds: results.map((r) => r.id) } })
      .then((data) => {
        if (cancelled) return;
        setGraphData(data);
        graphRunIdRef.current = searchMeta?.runId ?? null;
      })
      .catch((error) => {
        if (cancelled) return;
        setGraphError(
          error instanceof Error ? error.message : "Could not build the case connection graph.",
        );
      })
      .finally(() => {
        if (!cancelled) setGraphLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [graphView, results, searchMeta?.runId]);

  const executeSearch = async (currentQuery: string, currentFilters: Filters) => {
    const requestId = ++latestRequestId.current;
    setIsSearching(true);
    setHasSearched(true);
    setSearchError(null);
    const urlParams = new URLSearchParams();
    urlParams.set("case-description", currentQuery);
    currentFilters.courts.forEach((c) => urlParams.append("court", c));
    if (currentFilters.dateFrom) urlParams.set("dateFrom", currentFilters.dateFrom);
    if (currentFilters.dateTo) urlParams.set("dateTo", currentFilters.dateTo);
    if (currentFilters.sectionQuery) {
      urlParams.set("sectionQuery", currentFilters.sectionQuery);
      urlParams.set("matchEquivalents", String(currentFilters.matchEquivalents));
    }
    currentFilters.issues.forEach((i) => urlParams.append("issue", i));
    currentFilters.outcomes.forEach((o) => urlParams.append("outcome", o));
    window.history.replaceState(null, "", `${window.location.pathname}?${urlParams.toString()}`);

    const apiFilters = {
      court: currentFilters.courts.length === 1 ? currentFilters.courts[0] : "All Courts",
      year: "All Years",
      issue: currentFilters.issues.length === 1 ? currentFilters.issues[0] : "All Issues",
      outcome: currentFilters.outcomes.length === 1 ? currentFilters.outcomes[0] : "Any Outcome",
    };

    try {
      const data = await searchCasesFn({
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        data: { query: currentQuery, filters: apiFilters as any, topK: 10 },
      });
      if (requestId !== latestRequestId.current) return;
      setResults(data.results);
      setSearchMeta({
        runId: data.runId,
        corpusVersion: data.corpusVersion,
        modelVersion: data.modelVersion,
        retrievalMethod: data.retrievalMethod,
        extractedSignals: data.extractedSignals,
        latencyMs: data.latencyMs,
        caseCount: data.caseCount,
        chunkCount: data.chunkCount,
      });
      if (data.results.length > 0) {
        setExpandedId(data.results[0]?.id ?? null);
      } else {
        setExpandedId(null);
      }
    } catch (error) {
      if (requestId !== latestRequestId.current) return;
      console.error("Search failed:", error);
      const message =
        error instanceof Error ? error.message : "An unexpected error occurred while searching.";
      setSearchError(message);
      setResults([]);
      setSearchMeta(null);
    } finally {
      if (requestId === latestRequestId.current) setIsSearching(false);
    }
  };

  const resetFilters = () => {
    setFilters(DEFAULT_FILTERS);
    const urlParams = new URLSearchParams(window.location.search);
    urlParams.delete("court");
    urlParams.delete("dateFrom");
    urlParams.delete("dateTo");
    urlParams.delete("sectionQuery");
    urlParams.delete("matchEquivalents");
    urlParams.delete("issue");
    urlParams.delete("outcome");
    window.history.replaceState(null, "", `${window.location.pathname}?${urlParams.toString()}`);
  };

  const handleFilterChange = (newFilters: Filters) => {
    setFilters(newFilters);
    const urlParams = new URLSearchParams(window.location.search);
    urlParams.delete("court");
    urlParams.delete("dateFrom");
    urlParams.delete("dateTo");
    urlParams.delete("sectionQuery");
    urlParams.delete("matchEquivalents");
    urlParams.delete("issue");
    urlParams.delete("outcome");
    newFilters.courts.forEach((c) => urlParams.append("court", c));
    if (newFilters.dateFrom) urlParams.set("dateFrom", newFilters.dateFrom);
    if (newFilters.dateTo) urlParams.set("dateTo", newFilters.dateTo);
    if (newFilters.sectionQuery) {
      urlParams.set("sectionQuery", newFilters.sectionQuery);
      urlParams.set("matchEquivalents", String(newFilters.matchEquivalents));
    }
    newFilters.issues.forEach((i) => urlParams.append("issue", i));
    newFilters.outcomes.forEach((o) => urlParams.append("outcome", o));
    window.history.replaceState(null, "", `${window.location.pathname}?${urlParams.toString()}`);
  };

  const handleSearch = () => {
    executeSearch(query, filters);
  };

  const handleClear = () => {
    latestRequestId.current += 1;
    setQuery("");
    setHasSearched(false);
    setIsSearching(false);
    setFilters(DEFAULT_FILTERS);
    setResults([]);
    setSearchMeta(null);
    setSearchError(null);
    setGraphView(false);
    setGraphData(null);
    setGraphError(null);
    graphRunIdRef.current = null;
    window.history.replaceState(null, "", window.location.pathname);
  };

  const openResultFromGraph = (caseId: string) => {
    setGraphView(false);
    setExpandedId(caseId);
    requestAnimationFrame(() => {
      document
        .getElementById(`precedent-${caseId}`)
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  };

  const scrollToSearch = () => {
    const searchEl =
      document.getElementById("search-section") || document.getElementById("case-description");
    if (searchEl) {
      searchEl.scrollIntoView({ behavior: "smooth", block: "center" });
      const textarea = document.getElementById("case-description") as HTMLTextAreaElement | null;
      if (textarea) {
        setTimeout(() => textarea.focus(), 300);
      }
    }
  };

  const handleSelectCategory = (category: LegalCategory) => {
    setActiveCategory(category);
  };

  const filteredResults = useMemo(() => {
    const baseFiltered = results.filter((r) => {
      if (filters.courts.length > 0 && !filters.courts.includes(r.court)) return false;
      if (filters.dateFrom || filters.dateTo) {
        const caseDateStr = r.judgmentDate || `${r.year}-01-01`;
        const caseDate = new Date(caseDateStr);
        if (filters.dateFrom && caseDate < new Date(filters.dateFrom)) return false;
        if (filters.dateTo && caseDate > new Date(filters.dateTo)) return false;
      }
      if (filters.sectionQuery) {
        const sectionsToSearch = expandSection(filters.sectionQuery, filters.matchEquivalents);
        const searchTarget = [r.title, r.caseSummary, r.matchedEvidence, ...(r.legalIssues || [])]
          .join(" ")
          .toLowerCase();
        const hasMatch = sectionsToSearch.some((sec) => searchTarget.includes(sec.toLowerCase()));
        if (!hasMatch) return false;
      }
      if (filters.outcomes.length > 0 && !filters.outcomes.includes(r.outcome)) return false;
      if (filters.issues.length > 0 && !filters.issues.some((i) => r.filterIssues.includes(i)))
        return false;

      if (resultsQuery) {
        const q = resultsQuery.toLowerCase();
        const textTarget = [r.title, r.citation, r.caseSummary, r.matchedEvidence]
          .join(" ")
          .toLowerCase();
        if (!textTarget.includes(q)) return false;
      }
      return true;
    });

    // Sort
    return baseFiltered.sort((a, b) => {
      if (sortOrder === "newest" || sortOrder === "oldest") {
        const dateA = new Date(a.judgmentDate || `${a.year}-01-01`).getTime();
        const dateB = new Date(b.judgmentDate || `${b.year}-01-01`).getTime();
        return sortOrder === "newest" ? dateB - dateA : dateA - dateB;
      }
      if (sortOrder === "court") {
        return a.court.localeCompare(b.court);
      }
      return 0; // relevance is default order returned by API
    });
  }, [results, filters, resultsQuery, sortOrder]);

  const filterChips = useMemo(() => {
    const chips: { key: keyof Filters | "matchEquivalents"; label: string; value: string }[] = [];
    filters.courts.forEach((c) => chips.push({ key: "courts", label: "Court", value: c }));
    if (filters.dateFrom) chips.push({ key: "dateFrom", label: "From", value: filters.dateFrom });
    if (filters.dateTo) chips.push({ key: "dateTo", label: "To", value: filters.dateTo });
    if (filters.sectionQuery) {
      chips.push({ key: "sectionQuery", label: "Section", value: filters.sectionQuery });
    }
    filters.issues.forEach((i) => chips.push({ key: "issues", label: "Issue", value: i }));
    filters.outcomes.forEach((o) => chips.push({ key: "outcomes", label: "Outcome", value: o }));
    return chips;
  }, [filters]);

  const removeFilterChip = (chip: { key: keyof Filters | "matchEquivalents"; value: string }) => {
    if (chip.key === "courts") {
      handleFilterChange({ ...filters, courts: filters.courts.filter((c) => c !== chip.value) });
    } else if (chip.key === "issues") {
      handleFilterChange({ ...filters, issues: filters.issues.filter((i) => i !== chip.value) });
    } else if (chip.key === "outcomes") {
      handleFilterChange({
        ...filters,
        outcomes: filters.outcomes.filter((o) => o !== chip.value),
      });
    } else if (chip.key === "sectionQuery") {
      handleFilterChange({ ...filters, sectionQuery: "" });
    } else if (chip.key === "dateFrom") {
      handleFilterChange({ ...filters, dateFrom: null });
    } else if (chip.key === "dateTo") {
      handleFilterChange({ ...filters, dateTo: null });
    }
  };

  const filterCounts = useMemo(() => computeFacets(results), [results]);

  return (
    <div className="flex min-h-screen flex-col bg-background selection:bg-brand-blue/20">
      <Navbar
        activeCategory={activeCategory}
        onSelectCategory={handleSelectCategory}
        onSearchFocus={scrollToSearch}
      />

      <main className="flex-1">
        <div className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
            <aside
              className="lg:sticky lg:top-20 lg:h-fit lg:max-h-[calc(100vh-6rem)] lg:w-[360px] lg:shrink-0 lg:overflow-y-auto"
              aria-label="Result filters"
            >
              <button
                type="button"
                onClick={() => setFiltersOpen((open) => !open)}
                aria-expanded={filtersOpen}
                aria-controls="filter-panel"
                className="mb-3 inline-flex w-full items-center justify-between rounded-md border border-border bg-surface px-3 py-2.5 text-[13px] font-medium text-navy lg:hidden"
              >
                <span className="inline-flex items-center gap-2">
                  <SlidersHorizontal className="size-4" aria-hidden="true" />
                  Filters
                </span>
                <span className="text-muted-foreground">{filtersOpen ? "Hide" : "Show"}</span>
              </button>
              <div id="filter-panel" className={`${filtersOpen ? "block" : "hidden"} lg:block`}>
                <FilterPanel
                  filters={filters}
                  onChange={handleFilterChange}
                  onReset={resetFilters}
                  counts={filterCounts}
                />
              </div>
            </aside>

            <div className="min-w-0 flex-1">
              <SearchPanel
                query={query}
                onQueryChange={setQuery}
                onSearch={handleSearch}
                onClear={handleClear}
                isSearching={isSearching}
                selectedCategory={activeCategory}
                onSelectCategory={handleSelectCategory}
                filters={filters}
                onFiltersChange={handleFilterChange}
              />

              {!hasSearched ? (
                <section
                  id="recent-cases-heading"
                  aria-labelledby="corpus-heading"
                  className="mx-auto mt-8 max-w-4xl"
                >
                  <div className="rounded-xl border border-border bg-surface p-6 shadow-subtle sm:p-8">
                    <p className="text-[12px] font-semibold uppercase tracking-wider text-brand-blue">
                      Imported judgment corpus
                    </p>
                    <h2
                      id="corpus-heading"
                      className="mt-2 font-serif text-[25px] font-bold text-navy"
                    >
                      Imported Supreme Court and High Court judgments
                    </h2>
                    <p className="mt-3 text-[14px] leading-relaxed text-muted-foreground">
                      The keyless local engine searches the imported judgment collection with local
                      embeddings and exact legal-term matching. Metadata and source passages are
                      extracted from the supplied PDFs; records marked for review should be checked
                      against their source documents.
                    </p>
                    <div className="mt-5 grid gap-3 sm:grid-cols-3">
                      {[
                        ["Dense retrieval", "Local BGE-small passage embeddings"],
                        ["Lexical retrieval", "SQLite FTS5 legal-term search"],
                        ["Transparent fusion", "RRF with judgment-level grouping"],
                      ].map(([title, detail]) => (
                        <div
                          key={title}
                          className="rounded-md border border-border bg-background p-3"
                        >
                          <p className="text-[12.5px] font-semibold text-navy">{title}</p>
                          <p className="mt-1 text-[11.5px] text-muted-foreground">{detail}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                </section>
              ) : (
                <div className="pt-6">
                  <div className="mb-6 flex items-center justify-between">
                    <button
                      type="button"
                      onClick={() => setHasSearched(false)}
                      className="inline-flex items-center gap-2 rounded-lg border border-border bg-surface px-3.5 py-1.5 text-[13px] font-medium text-navy hover:bg-accent hover:text-brand-blue transition-colors shadow-2xs"
                    >
                      <ArrowLeft className="size-4" />
                      <span>Back to corpus overview</span>
                    </button>
                  </div>

                  <section className="min-w-0" aria-label="Search results">
                    <div className="rounded-lg border border-brand-blue/30 bg-brand-blue/5 p-3.5 text-[12.5px] leading-relaxed text-navy">
                      <strong>Local hybrid retrieval:</strong> Substantive dense retrieval and
                      deduplicated legal-term search are fused at judgment level. A transparent
                      legal reranker then checks controlling statutes, provisions, domain, relief,
                      material facts and contradictions before applying authority as a tie-breaker.
                      Each result shows its relevance basis; Precision@5 is measured separately on
                      reviewed queries, not presented as a per-case confidence score. Outcomes must
                      be verified against the source judgment.
                    </div>

                    {searchMeta && !isSearching && (
                      <div className="mt-3 rounded-md border border-border bg-surface px-3.5 py-3 text-[12px] text-muted-foreground">
                        <div className="flex flex-wrap gap-x-4 gap-y-1">
                          <span>Corpus: {searchMeta.corpusVersion}</span>
                          <span>Model: {searchMeta.modelVersion}</span>
                          <span>Search time: {searchMeta.latencyMs} ms</span>
                          <span>{searchMeta.caseCount.toLocaleString()} indexed judgments</span>
                          <span>{searchMeta.chunkCount.toLocaleString()} searchable passages</span>
                        </div>
                        {searchMeta.extractedSignals.length > 0 && (
                          <div className="mt-2 flex flex-wrap items-center gap-1.5">
                            <span className="font-medium text-navy">Detected signals:</span>
                            {searchMeta.extractedSignals.map((signal) => (
                              <span
                                key={signal}
                                className="rounded-md border border-border bg-background px-2 py-0.5 text-navy"
                              >
                                {signal}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    <div className="mt-6 flex flex-col gap-4 border-b border-border pb-4">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="flex items-center gap-2">
                          <h2 className="text-[15px] font-bold text-navy">
                            {filteredResults.length} precedent
                            {filteredResults.length === 1 ? "" : "s"}
                          </h2>
                          {results.length > 0 && (
                            <span className="text-[13px] text-muted-foreground">
                              of {results.length} retrieved
                            </span>
                          )}
                        </div>

                        <div className="flex items-center gap-3">
                          <div className="relative">
                            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
                            <input
                              type="text"
                              placeholder="Search within results..."
                              value={resultsQuery}
                              onChange={(e) => setResultsQuery(e.target.value)}
                              className="w-48 rounded-md border border-border bg-background pl-8 pr-2.5 py-1.5 text-[12.5px] text-foreground focus:outline-none focus:ring-2 focus:ring-brand-blue"
                            />
                          </div>
                          <select
                            value={sortOrder}
                            onChange={(e) => setSortOrder(e.target.value)}
                            className="rounded-md border border-border bg-background px-2.5 py-1.5 text-[12.5px] text-foreground focus:outline-none focus:ring-2 focus:ring-brand-blue"
                          >
                            <option value="relevance">Relevance</option>
                            <option value="newest">Newest first</option>
                            <option value="oldest">Oldest first</option>
                            <option value="court">Court hierarchy</option>
                          </select>
                          <div className="flex items-center rounded-md border border-border bg-background p-0.5">
                            <button
                              type="button"
                              onClick={() => {
                                setIsCompact(true);
                                setGraphView(false);
                              }}
                              className={`rounded-sm p-1 ${isCompact && !graphView ? "bg-muted text-navy" : "text-muted-foreground hover:text-navy"}`}
                              title="Compact view"
                            >
                              <AlignJustify className="size-3.5" />
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setIsCompact(false);
                                setGraphView(false);
                              }}
                              className={`rounded-sm p-1 ${!isCompact && !graphView ? "bg-muted text-navy" : "text-muted-foreground hover:text-navy"}`}
                              title="Detailed view"
                            >
                              <LayoutList className="size-3.5" />
                            </button>
                            <button
                              type="button"
                              onClick={() => setGraphView((current) => !current)}
                              className={`rounded-sm p-1 ${graphView ? "bg-muted text-navy" : "text-muted-foreground hover:text-navy"}`}
                              title="Graph view: how these cases connect"
                            >
                              <Network className="size-3.5" />
                            </button>
                          </div>
                        </div>
                      </div>

                      {filterChips.length > 0 && (
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-[11.5px] font-medium text-muted-foreground uppercase tracking-wide mr-1">
                            Active filters:
                          </span>
                          {filterChips.map((chip, idx) => (
                            <span
                              key={idx}
                              className="inline-flex items-center gap-1 rounded-full border border-brand-blue/20 bg-brand-blue/5 px-2 py-0.5 text-[12px] text-brand-blue"
                            >
                              {chip.label}: {chip.value}
                              <button
                                type="button"
                                onClick={() => removeFilterChip(chip)}
                                className="ml-0.5 rounded-full p-0.5 hover:bg-brand-blue/20"
                              >
                                <X className="size-3" />
                              </button>
                            </span>
                          ))}
                          <button
                            type="button"
                            onClick={resetFilters}
                            className="ml-1 text-[12px] font-medium text-muted-foreground hover:text-navy hover:underline"
                          >
                            Clear all
                          </button>
                        </div>
                      )}
                    </div>

                    {isSearching ? (
                      <ResultSkeleton />
                    ) : searchError ? (
                      <div className="py-12 text-center rounded-xl border border-dashed border-red-300 bg-red-50/50 mt-6">
                        <p className="text-[15px] font-medium text-red-700">Search failed</p>
                        <p className="mt-2 text-[13px] text-red-600/80 max-w-md mx-auto">
                          {searchError}
                        </p>
                        <button
                          type="button"
                          onClick={() => executeSearch(query, filters)}
                          className="mt-4 rounded-md bg-navy px-4 py-2 text-[13px] font-medium text-primary-foreground hover:bg-navy/90"
                        >
                          Try again
                        </button>
                      </div>
                    ) : graphView ? (
                      <div className="mt-6">
                        {graphLoading ? (
                          <ResultSkeleton />
                        ) : graphError ? (
                          <div className="py-12 text-center rounded-xl border border-dashed border-red-300 bg-red-50/50">
                            <p className="text-[15px] font-medium text-red-700">
                              Could not build the graph
                            </p>
                            <p className="mt-2 text-[13px] text-red-600/80 max-w-md mx-auto">
                              {graphError}
                            </p>
                          </div>
                        ) : graphData ? (
                          <CaseGraph
                            nodes={graphData.nodes}
                            edges={graphData.edges}
                            citationEdgeCount={graphData.citationEdgeCount}
                            statuteEdgeCount={graphData.statuteEdgeCount}
                            resultIds={results.map((r) => r.id)}
                            onOpenResult={openResultFromGraph}
                          />
                        ) : null}
                      </div>
                    ) : filteredResults.length === 0 ? (
                      <div className="py-16 text-center rounded-xl border border-dashed border-border bg-surface mt-6">
                        <p className="text-[15px] font-medium text-muted-foreground">
                          No indexed precedents match this query and the selected filters.
                        </p>
                        <button
                          type="button"
                          onClick={resetFilters}
                          className="mt-4 rounded-md bg-navy px-4 py-2 text-[13px] font-medium text-primary-foreground hover:bg-navy/90"
                        >
                          Reset all filters
                        </button>
                      </div>
                    ) : (
                      <div className="divide-y divide-border mt-4">
                        {filteredResults.map((precedent) => (
                          <PrecedentItem
                            key={precedent.id}
                            precedent={precedent}
                            expanded={expandedId === precedent.id}
                            onToggle={() =>
                              setExpandedId((current) =>
                                current === precedent.id ? null : precedent.id,
                              )
                            }
                            searchQuery={query}
                            sectionQuery={filters.sectionQuery}
                            activeIssues={filters.issues}
                            isCompact={isCompact}
                          />
                        ))}
                      </div>
                    )}
                  </section>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>

      <SiteFooter />
    </div>
  );
}
