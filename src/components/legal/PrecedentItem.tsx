import {
  ChevronDown,
  ExternalLink,
  CheckCircle2,
  XCircle,
  Clock,
  HelpCircle,
  PieChart,
  CornerUpLeft,
} from "lucide-react";
import type { Precedent } from "@/data/precedents";

function HighlightedEvidence({
  text,
  phrases,
  searchQuery,
  sectionQuery,
  activeIssues,
}: {
  text: string;
  phrases: string[];
  searchQuery?: string | undefined;
  sectionQuery?: string | undefined;
  activeIssues?: string[] | undefined;
}) {
  // Cap at 3 sentences
  const sentences = text.match(/[^.!?]+[.!?]+/g) || [text];
  const cappedText = sentences.slice(0, 3).join("").trim() || text;

  // Gather all words to highlight from query, section query, and active issues
  const wordsToHighlight = new Set<string>();

  if (searchQuery) {
    searchQuery
      .split(/\s+/)
      .filter((w) => w.length > 3)
      .forEach((w) => wordsToHighlight.add(w.toLowerCase()));
  }
  if (sectionQuery) {
    sectionQuery
      .split(/\s+/)
      .filter((w) => w.length > 0)
      .forEach((w) => wordsToHighlight.add(w.toLowerCase()));
  }
  if (activeIssues) {
    activeIssues.forEach((issue) => {
      issue
        .split(/\s+/)
        .filter((w) => w.length > 3)
        .forEach((w) => wordsToHighlight.add(w.toLowerCase()));
    });
  }

  // add original phrases
  const escaped = phrases.map((phrase) => phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const allTerms = Array.from(wordsToHighlight)
    .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .concat(escaped);

  const pattern = allTerms.length > 0 ? new RegExp(`(${allTerms.join("|")})`, "gi") : null;
  const parts = pattern ? cappedText.split(pattern) : [cappedText];

  return (
    <p className="line-clamp-6 text-[13.5px] leading-relaxed text-foreground">
      {parts.map((part, index) => {
        if (!pattern) return <span key={index}>{part}</span>;
        const lowerPart = part.toLowerCase();

        let hlClass = "";
        if (searchQuery && searchQuery.toLowerCase().includes(lowerPart) && part.length > 3)
          hlClass = "hl-query";
        else if (sectionQuery && sectionQuery.toLowerCase().includes(lowerPart) && part.length > 0)
          hlClass = "hl-section";
        else if (phrases.some((p) => p.toLowerCase() === lowerPart))
          hlClass = "bg-brand-blue/12 text-navy";
        else if (activeIssues?.some((i) => i.toLowerCase().includes(lowerPart)) && part.length > 3)
          hlClass = "bg-brand-blue/12 text-navy";

        if (hlClass) {
          return (
            <mark key={index} className={`${hlClass} px-0.5 font-medium`}>
              {part}
            </mark>
          );
        }
        return <span key={index}>{part}</span>;
      })}
    </p>
  );
}

type BadgeTone = "success" | "danger" | "info" | "neutral" | "unknown";

function getBadgeTone(value: string): BadgeTone {
  const lower = value.toLowerCase();

  if (
    lower.includes("applicant/petitioner/appellant succeeded") ||
    lower.includes("petitioner succeeded") ||
    lower.includes("appellant succeeded") ||
    lower.includes("applicant succeeded") ||
    lower.includes("bail granted") ||
    lower.includes("relief granted") ||
    lower.includes("impugned decision set aside") ||
    lower.includes("allow") ||
    lower.includes("grant")
  ) {
    return "success";
  }

  if (
    lower.includes("dismiss") ||
    lower.includes("reject") ||
    lower.includes("respondent/state succeeded") ||
    lower.includes("state succeeded") ||
    lower.includes("conviction upheld") ||
    lower.includes("overruled")
  ) {
    return "danger";
  }

  if (
    lower.includes("ongoing") ||
    lower.includes("pending") ||
    lower.includes("appeal/revision stage") ||
    lower.includes("appeal stage") ||
    lower.includes("trial ongoing")
  ) {
    return "info";
  }

  if (lower.includes("disposed") || lower.includes("closed") || lower.includes("final")) {
    return "neutral";
  }

  if (
    lower.includes("not stated") ||
    lower.includes("verify") ||
    lower.includes("missing") ||
    lower.includes("null") ||
    lower === ""
  ) {
    return "unknown";
  }

  return "unknown";
}

function shortenBadgeValue(value: string): string {
  if (value.includes("Appellant / petitioner su")) return "Petitioner won";
  if (value.includes("Accused / applicant su")) return "Applicant won";
  if (value.includes("Respondent / State side su")) return "State won";
  if (value.includes("Not stated - verify judg")) return "Unverified";
  if (value.includes("Appeal / revision stage")) return "Appeal stage";
  if (value.includes("Matter disposed")) return "Disposed";
  return value;
}

type WinnerTone = "green" | "red" | "blue" | "purple" | "amber";

function getWinnerTone(value: string): WinnerTone {
  const lower = value.toLowerCase();

  // RED MUST BE CHECKED BEFORE GREEN
  if (
    lower.includes("respondent succeeded") ||
    lower.includes("respondent/state side succeeded") ||
    lower.includes("state won") ||
    lower.includes("state succeeded") ||
    lower.includes("dismissed") ||
    lower.includes("appeal dismissed") ||
    lower.includes("petition dismissed") ||
    lower.includes("bail rejected") ||
    lower.includes("bail declined") ||
    lower.includes("application rejected") ||
    lower.includes("conviction upheld") ||
    lower.includes("conviction affirmed") ||
    lower.includes("slp dismissed")
  ) {
    return "red";
  }

  // PURPLE MUST BE CHECKED BEFORE GREEN
  if (
    lower.includes("remanded") ||
    lower.includes("remitted") ||
    lower.includes("matter remanded") ||
    lower.includes("remanded/no final winner") ||
    lower.includes("no final winner") ||
    lower.includes("sent back") ||
    lower.includes("withdrawn") ||
    lower.includes("permitted to be withdrawn") ||
    lower.includes("disposed as infructuous") ||
    lower.includes("infructuous") ||
    lower.includes("rendered academic") ||
    lower.includes("transferred")
  ) {
    return "purple";
  }

  // GREEN
  if (
    lower.includes("appellant succeeded") ||
    lower.includes("appellant/petitioner succeeded") ||
    lower.includes("petitioner succeeded") ||
    lower.includes("petitioner won") ||
    lower.includes("applicant won") ||
    lower.includes("accused/applicant succeeded") ||
    lower.includes("accused succeeded") ||
    lower.includes("bail granted") ||
    lower.includes("relief granted") ||
    lower.includes("appeal allowed") ||
    lower.includes("petition allowed") ||
    lower.includes("impugned decision set aside") ||
    lower.includes("conviction set aside") ||
    lower.includes("proceedings quashed") ||
    lower.includes("acquitted")
  ) {
    return "green";
  }

  // BLUE
  if (
    lower.includes("partly allowed") ||
    lower.includes("partially allowed") ||
    lower.includes("partial relief") ||
    lower.includes("partial/mixed relief") ||
    lower.includes("mixed relief") ||
    lower.includes("relief partly granted")
  ) {
    return "blue";
  }

  return "amber";
}

function shortenWinnerValue(value: string): string {
  if (value.includes("Appellant / petitioner su")) return "Appellant won";
  if (value.includes("Accused / applicant su")) return "Applicant won";
  if (value.includes("Respondent / State side su")) return "State won";
  if (value.includes("Remanded / no final winner")) return "Remanded";
  if (value.includes("Partial / mixed relief")) return "Partly allowed";
  if (value.includes("Not stated - verify judg")) return "Unverified";
  return value;
}

function WinnerBadge({ value }: { value: string }) {
  const tone = getWinnerTone(value);
  const shortened = shortenWinnerValue(value);

  let Icon = HelpCircle;
  if (tone === "green") Icon = CheckCircle2;
  else if (tone === "red") Icon = XCircle;
  else if (tone === "blue") Icon = PieChart;
  else if (tone === "purple") Icon = CornerUpLeft;

  const bgVar = `var(--winner-${tone}-bg)`;
  const fgVar = `var(--winner-${tone}-fg)`;

  return (
    <div
      className="inline-flex items-center gap-1.5 whitespace-nowrap px-[10px] py-[4px] rounded-[6px]"
      style={{ backgroundColor: bgVar, color: fgVar }}
      title={value}
    >
      <Icon className="size-[13px] shrink-0" aria-hidden="true" />
      <div className="flex items-center gap-1">
        <span className="text-[10px] uppercase tracking-[0.04em] opacity-75">RESULT</span>
        <span className="text-[12.5px] font-semibold leading-none pt-px">{shortened}</span>
      </div>
    </div>
  );
}

function StatusBadge({
  label,
  value,
  isPrimary = false,
}: {
  label: string;
  value: string;
  isPrimary?: boolean;
}) {
  const tone = getBadgeTone(value);
  const shortened = shortenBadgeValue(value);

  let Icon = null;
  if (isPrimary) {
    if (tone === "success") Icon = CheckCircle2;
    else if (tone === "danger") Icon = XCircle;
    else if (tone === "info") Icon = Clock;
    else Icon = HelpCircle;
  }

  const showLabel = isPrimary || label === "Stage" || label === "Trial";
  const baseClasses =
    "inline-flex items-center gap-1.5 whitespace-nowrap px-[9px] py-[3px] rounded-[6px] h-[22px]";

  let colorClasses = "";
  let style: React.CSSProperties = {};

  if (isPrimary) {
    colorClasses = `bg-badge-${tone}-bg text-badge-${tone}-text`;
  } else {
    colorClasses = "bg-transparent border border-solid";
    style = {
      borderColor: `color-mix(in oklch, var(--color-badge-${tone}-text) 35%, transparent)`,
      color: `color-mix(in oklch, var(--color-badge-${tone}-text) 80%, transparent)`,
    };
  }

  return (
    <div className={`${baseClasses} ${colorClasses}`} style={style} title={value}>
      {Icon && <Icon className="size-[12px] shrink-0" aria-hidden="true" />}
      <div className="flex items-center gap-1">
        {showLabel && (
          <span className="text-[10px] uppercase tracking-[0.04em] opacity-70">{label}:</span>
        )}
        <span className="text-[12px] font-medium leading-none pt-px">{shortened}</span>
      </div>
    </div>
  );
}

interface PrecedentItemProps {
  precedent: Precedent;
  expanded: boolean;
  onToggle: () => void;
  searchQuery?: string;
  sectionQuery?: string;
  activeIssues?: string[];
  isCompact?: boolean;
}

export function PrecedentItem({
  precedent,
  expanded,
  onToggle,
  searchQuery,
  sectionQuery,
  activeIssues,
  isCompact = false,
}: PrecedentItemProps) {
  const panelId = `why-${precedent.id}`;

  return (
    <article id={`precedent-${precedent.id}`} className="py-7 scroll-mt-24">
      <div className="flex items-start gap-4">
        <span
          aria-hidden="true"
          className="mt-0.5 min-w-6 font-serif text-[15px] font-semibold text-muted-foreground tabular-nums"
        >
          {precedent.rank}.
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-col gap-4 min-[900px]:flex-row min-[900px]:items-start min-[900px]:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                <h3 className="text-[19px] leading-snug font-semibold text-navy">
                  <span className="sr-only">Result {precedent.rank}: </span>
                  {precedent.title}
                </h3>
              </div>

              <dl className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12.5px] text-muted-foreground">
                <div className="flex gap-1">
                  <dt className="sr-only">Court</dt>
                  <dd>{precedent.court}</dd>
                </div>
                <span aria-hidden="true">·</span>
                <div className="flex gap-1">
                  <dt className="sr-only">Year</dt>
                  <dd>{precedent.year}</dd>
                </div>
                <span aria-hidden="true">·</span>
                <div className="flex gap-1">
                  <dt className="sr-only">Citation</dt>
                  <dd className="font-mono text-[12px]">{precedent.citation}</dd>
                </div>
                <span aria-hidden="true">·</span>
                <div className="flex gap-1.5">
                  <dt className="text-muted-foreground">Final rank</dt>
                  <dd className="font-medium text-teal">#{precedent.rank}</dd>
                </div>
              </dl>
            </div>

            <div
              className="mt-3 min-[900px]:mt-0 flex flex-wrap gap-[6px] min-[900px]:justify-end shrink-0 items-center"
              aria-label="Status badges"
            >
              <WinnerBadge value={precedent.winner} />
              <StatusBadge label="Trial" value={precedent.trialStatus} />
              <StatusBadge label="Stage" value={precedent.caseStage} />
            </div>
          </div>

          {!isCompact && (
            <p className="mt-2 text-[13px] text-muted-foreground">
              <span className="text-navy">Procedural posture:</span> {precedent.posture}
            </p>
          )}

          {!isCompact && (
            <ul className="mt-3 flex flex-wrap gap-2">
              {precedent.legalIssues.map((issue) => (
                <li
                  key={issue}
                  className="rounded-md border border-border px-2 py-0.5 text-[11.5px] text-navy"
                >
                  {issue}
                </li>
              ))}
            </ul>
          )}

          <div className="mt-4 rounded-r-md border-l-2 border-brand-blue bg-evidence px-3.5 py-3">
            <p className="mb-1 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
              Query-focused case summary
            </p>
            <HighlightedEvidence
              text={precedent.caseSummary}
              phrases={precedent.highlightPhrases}
              searchQuery={searchQuery}
              sectionQuery={sectionQuery}
              activeIssues={activeIssues}
            />
            {precedent.evidenceLocator && !isCompact && (
              <p className="mt-2 text-[11.5px] text-muted-foreground">
                Primary matched passage: {precedent.evidenceLocator.section} ·{" "}
                {precedent.evidenceLocator.paragraph}
              </p>
            )}
          </div>

          {!isCompact &&
            (() => {
              let displayOutcome = precedent.outcome || "";
              let isAbsent = false;
              const lower = displayOutcome.toLowerCase();
              if (
                !displayOutcome ||
                lower === "not stated" ||
                lower === "not stated - verify judgment"
              ) {
                displayOutcome = "Not stated — verify against source judgment";
                isAbsent = true;
              } else {
                displayOutcome = displayOutcome.charAt(0).toUpperCase() + displayOutcome.slice(1);
              }

              return (
                <div
                  className="my-[12px] flex flex-col rounded-r-[8px] rounded-l-none border border-l-[3px] px-[14px] py-[10px]"
                  style={{
                    backgroundColor: "var(--outcome-bg)",
                    borderColor: "var(--outcome-border)",
                    borderLeftColor: "var(--brand-blue)",
                    color: "var(--outcome-text)",
                  }}
                >
                  <span className="text-[10px] font-bold uppercase tracking-[0.05em] text-brand-blue">
                    Recorded result
                  </span>
                  <span
                    className={`mt-0.5 text-[15px] font-semibold leading-snug ${isAbsent ? "opacity-80 font-medium" : "opacity-100"}`}
                  >
                    {displayOutcome}
                  </span>
                </div>
              );
            })()}

          {!isCompact && (
            <p className="mt-2 text-[11.5px] leading-relaxed text-muted-foreground">
              <span className="font-semibold text-navy">Relevance basis:</span>{" "}
              {precedent.relevanceBasis.join(" · ")}
            </p>
          )}

          {!isCompact && (
            <p className="mt-2 text-[11.5px] leading-relaxed text-muted-foreground">
              <span className="font-semibold text-navy">Authority context:</span>{" "}
              {precedent.authorityBasis.join(" · ")} · Bench: {precedent.benchStrength} ·
              Adjustment: {precedent.authorityScore.toFixed(6)}
            </p>
          )}

          {!isCompact && (precedent.denseRank || precedent.lexicalRank) && (
            <p className="mt-2 text-[11.5px] text-muted-foreground">
              Retrieval trace: dense rank {precedent.denseRank ?? "not in candidate set"} · lexical
              rank {precedent.lexicalRank ?? "not in candidate set"}
            </p>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={onToggle}
              aria-expanded={expanded}
              aria-controls={panelId}
              className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-[12.5px] font-medium text-navy hover:bg-accent"
            >
              <ChevronDown
                className={`size-3.5 transition-transform ${expanded ? "rotate-180" : ""}`}
                aria-hidden="true"
              />
              Why it matched
            </button>

            <a
              href={precedent.sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-[12.5px] font-medium text-navy transition-colors hover:bg-accent hover:text-brand-blue"
            >
              <ExternalLink className="size-3.5" aria-hidden="true" />
              Open source document
            </a>
          </div>

          <div
            id={panelId}
            hidden={!expanded}
            className="mt-4 rounded-md border border-border bg-surface p-4"
          >
            <dl className="space-y-3 text-[13px]">
              <div>
                <dt className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
                  Case-stage evidence
                </dt>
                <dd className="mt-1 text-foreground">{precedent.caseStageEvidence}</dd>
              </div>
              <div>
                <dt className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
                  Result evidence
                </dt>
                <dd className="mt-1 text-foreground">{precedent.outcomeEvidence}</dd>
              </div>
              <div>
                <dt className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
                  Shared facts
                </dt>
                <dd className="mt-1 text-foreground">{precedent.explanation.sharedFacts}</dd>
              </div>
              <div>
                <dt className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
                  Shared legal issues
                </dt>
                <dd className="mt-1 text-foreground">{precedent.explanation.sharedLegalIssues}</dd>
              </div>
              <div>
                <dt className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
                  Procedural posture
                </dt>
                <dd className="mt-1 text-foreground">{precedent.explanation.proceduralPosture}</dd>
              </div>
              <div>
                <dt className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
                  Matching legal terms
                </dt>
                <dd className="mt-1.5 flex flex-wrap gap-2">
                  {precedent.explanation.matchingTerms.map((term) => (
                    <span
                      key={term}
                      className="rounded-md bg-muted px-2 py-0.5 font-mono text-[11.5px] text-navy"
                    >
                      {term}
                    </span>
                  ))}
                </dd>
              </div>
              <div>
                <dt className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
                  Relation
                </dt>
                <dd className="mt-1 text-foreground">{precedent.explanation.relation}</dd>
              </div>
              <div>
                <dt className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
                  Match points
                </dt>
                <dd>
                  <ul className="mt-1 list-disc space-y-1 pl-4 text-foreground">
                    {precedent.whyItMatched.map((point) => (
                      <li key={point}>{point}</li>
                    ))}
                  </ul>
                </dd>
              </div>
            </dl>
          </div>
        </div>
      </div>
    </article>
  );
}
