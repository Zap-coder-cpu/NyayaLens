export type CourtLevel = "Supreme Court" | "High Court";

export type LegalCategory = "All" | "Bail & Personal Liberty" | "Fraud & Economic Offences";

export interface CategoryInfo {
  id: LegalCategory;
  label: string;
  shortLabel: string;
  badgeColor: string;
  iconName: string;
  description: string;
  sampleQuery: string;
}

export const CATEGORIES: CategoryInfo[] = [
  {
    id: "All",
    label: "Imported Corpus",
    shortLabel: "All",
    badgeColor: "bg-muted text-muted-foreground border-border",
    iconName: "Scale",
    description: "Search every indexed Supreme Court and High Court judgment in the local corpus.",
    sampleQuery:
      "The applicant seeks regular bail after prolonged custody. The investigation is complete and the prosecution relies mainly on documentary evidence.",
  },
  {
    id: "Bail & Personal Liberty",
    label: "Bail & Personal Liberty",
    shortLabel: "Bail / Liberty",
    badgeColor: "bg-blue-50 text-blue-700 border-blue-200",
    iconName: "KeyRound",
    description: "Regular bail, anticipatory bail, default bail, custody duration and Article 21.",
    sampleQuery:
      "The applicant seeks regular bail after prolonged custody. The charge sheet has been filed, the evidence is documentary, and there is no flight risk or allegation of witness interference.",
  },
  {
    id: "Fraud & Economic Offences",
    label: "Economic Offence Bail",
    shortLabel: "Economic Bail",
    badgeColor: "bg-emerald-50 text-emerald-800 border-emerald-200",
    iconName: "Banknote",
    description:
      "Contrasting bail principles in financial-crime and money-laundering investigations.",
    sampleQuery:
      "The applicant requests anticipatory bail in a PMLA money-laundering investigation where the agency argues that custodial interrogation is required and the investigation remains active.",
  },
];

export interface Precedent {
  id: string;
  rank: number;
  title: string;
  court: string;
  year: string;
  judgmentDate?: string;
  category: string;
  citation: string;
  posture: string;
  legalIssues: string[];
  filterIssues: string[];
  matchedEvidence: string;
  caseSummary: string;
  highlightPhrases: string[];
  outcome: string;
  matterStatus: string;
  trialStatus: string;
  winner: string;
  caseStage: string;
  caseStageConfidence: string;
  caseStageEvidence: string;
  outcomeRelief: string;
  outcomeEvidence: string;
  relevanceBasis: string[];
  authorityScore: number;
  authorityBasis: string[];
  benchStrength: string;
  whyItMatched: string[];
  explanation: {
    sharedFacts: string;
    sharedLegalIssues: string;
    proceduralPosture: string;
    matchingTerms: string[];
    relation: string;
  };
  sourceUrl: string;
  evidenceLocator: { section: string; paragraph: string };
  reasonCodes: string[];
  denseRank?: number | null;
  lexicalRank?: number | null;
  retrievalScore: number;
}

export const FILTER_ISSUES = [
  "Regular Bail",
  "Anticipatory Bail",
  "Default Bail",
  "Prolonged Custody",
  "Documentary Evidence",
  "Witness Interference",
  "Flight Risk",
  "Criminal Law",
  "Constitutional Law",
  "Service Law",
  "Taxation",
  "Arbitration",
  "Property / Land",
  "Succession / Inheritance",
  "Probate / Wills",
  "Tenancy / Rent Control",
  "Family / Matrimonial",
  "Motor Vehicles / Compensation",
  "Consumer Law",
  "Insolvency",
  "Environmental Law",
  "Narcotics / NDPS",
  "Economic Offences / PMLA",
  "Cheque Dishonour",
  "Civil Procedure",
  "Quashing of Criminal Proceedings",
] as const;

export const YEARS = [
  "2026",
  "2025",
  "2024",
  "2023",
  "2022",
  "2021",
  "2020",
  "2019",
  "2018",
  "2017",
  "2016",
  "2015",
] as const;

export const COURTS = ["Supreme Court", "High Court"] as const;

export const OUTCOME_FILTERS = [
  "Petitioner / Appellant side succeeded",
  "Respondent / State side succeeded",
  "Partial / mixed relief",
  "Remanded / no final winner",
] as const;

export const DEFAULT_QUERY =
  "The applicant seeks regular bail after prolonged custody. The investigation is complete and the prosecution relies mainly on documentary evidence. There is no allegation that the applicant may abscond or influence witnesses, and the trial is unlikely to conclude soon.";
