export interface HighCourt {
  id: string;
  name: string;
  benches?: string[];
}

export const HIGH_COURTS: HighCourt[] = [
  { id: "allahabad", name: "Allahabad", benches: ["Lucknow"] },
  { id: "andhra-pradesh", name: "Andhra Pradesh" },
  { id: "bombay", name: "Bombay", benches: ["Nagpur", "Aurangabad", "Goa"] },
  { id: "calcutta", name: "Calcutta", benches: ["Port Blair", "Jalpaiguri"] },
  { id: "chhattisgarh", name: "Chhattisgarh" },
  { id: "delhi", name: "Delhi" },
  { id: "gauhati", name: "Gauhati", benches: ["Kohima", "Aizawl", "Itanagar"] },
  { id: "gujarat", name: "Gujarat" },
  { id: "himachal-pradesh", name: "Himachal Pradesh" },
  {
    id: "jammu-kashmir-ladakh",
    name: "Jammu & Kashmir and Ladakh",
    benches: ["Srinagar", "Jammu"],
  },
  { id: "jharkhand", name: "Jharkhand" },
  { id: "karnataka", name: "Karnataka", benches: ["Dharwad", "Kalaburagi"] },
  { id: "kerala", name: "Kerala" },
  { id: "madhya-pradesh", name: "Madhya Pradesh", benches: ["Indore", "Gwalior"] },
  { id: "madras", name: "Madras", benches: ["Madurai"] },
  { id: "manipur", name: "Manipur" },
  { id: "meghalaya", name: "Meghalaya" },
  { id: "orissa", name: "Orissa" },
  { id: "patna", name: "Patna" },
  { id: "punjab-haryana", name: "Punjab and Haryana" },
  { id: "rajasthan", name: "Rajasthan", benches: ["Jaipur"] },
  { id: "sikkim", name: "Sikkim" },
  { id: "telangana", name: "Telangana" },
  { id: "tripura", name: "Tripura" },
  { id: "uttarakhand", name: "Uttarakhand" },
];

export interface Act {
  id: string;
  label: string;
  sections: string[];
}

export const ACTS: Act[] = [
  { id: "bnss-crpc", label: "BNSS / CrPC", sections: ["480", "482", "483", "187", "528", "223"] },
  { id: "bns-ipc", label: "BNS / IPC", sections: ["103", "105", "115", "316", "318", "351"] },
  { id: "bsa-evidence", label: "BSA / Evidence Act", sections: ["23", "61", "63"] },
  { id: "ndps", label: "NDPS Act", sections: ["8", "20", "21", "27A", "37"] },
  { id: "pmla", label: "PMLA", sections: ["3", "4", "19", "45", "50"] },
  { id: "uapa", label: "UAPA", sections: ["15", "18", "43D"] },
  { id: "nia", label: "Negotiable Instruments Act", sections: ["138", "139", "141", "142"] },
  { id: "pca", label: "Prevention of Corruption Act", sections: ["7", "13", "17A", "19"] },
  { id: "cpc", label: "CPC", sections: ["9", "11", "151", "O7R11", "O39"] },
  { id: "companies", label: "Companies Act", sections: ["230", "241", "242", "447"] },
  { id: "ibc", label: "IBC", sections: ["7", "9", "10", "12A", "31"] },
  { id: "arbitration", label: "Arbitration Act", sections: ["8", "9", "11", "34", "37"] },
  { id: "mva", label: "Motor Vehicles Act", sections: ["163A", "166", "173"] },
  { id: "constitution", label: "Constitution", sections: ["14", "19", "21", "32", "226", "227"] },
];

export const SECTION_EQUIVALENTS: Record<string, string[]> = {
  // CrPC ↔ BNSS
  "437": ["480"],
  "480": ["437"],
  "438": ["482"],
  "482": ["438"],
  "439": ["483"],
  "483": ["439"],
  "167": ["187"],
  "187": ["167"],
  // IPC ↔ BNS
  "302": ["103"],
  "103": ["302"],
  "420": ["318"],
  "318": ["420"],
  "498A": ["85"],
  "85": ["498A"],
  "376": ["64"],
  "64": ["376"],
  "304B": ["80"],
  "80": ["304B"],
};

export function expandSection(section: string, mappingOn: boolean): string[] {
  const normalized = section.trim();
  if (!mappingOn) {
    return [normalized];
  }
  const equivalents = SECTION_EQUIVALENTS[normalized] || [];
  return [normalized, ...equivalents];
}
