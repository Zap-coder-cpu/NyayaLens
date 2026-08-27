import { FileSearch } from "lucide-react";

export function SiteHeader() {
  return (
    <header className="h-[70px] border-b border-border bg-surface">
      <div className="mx-auto flex h-full max-w-[1280px] items-center justify-between gap-4 px-4 sm:px-6">
        <div className="flex items-center gap-3">
          <FileSearch className="size-5 shrink-0 text-brand-blue" aria-hidden="true" />
          <div className="leading-tight">
            <p className="font-serif text-[17px] font-semibold text-navy">Nyayalens</p>
            <p className="text-[12px] text-muted-foreground">Precedent Retrieval Prototype</p>
          </div>
        </div>
        <span className="rounded-md border border-saffron/60 px-2.5 py-1 text-[11px] font-medium tracking-wide text-saffron uppercase">
          Demonstration Only
        </span>
      </div>
    </header>
  );
}
