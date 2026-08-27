import { useState, useRef, useEffect } from "react";
import {
  Scale,
  ShieldAlert,
  Building2,
  KeyRound,
  ShieldCheck,
  HeartHandshake,
  Banknote,
  Menu,
  X,
  Search,
  ChevronDown,
  Check,
  Layers,
  BookOpen,
} from "lucide-react";
import { CATEGORIES, type LegalCategory } from "@/data/precedents";
import { ModeToggle } from "@/components/mode-toggle";

interface NavbarProps {
  activeCategory: LegalCategory;
  onSelectCategory: (category: LegalCategory) => void;
  onSearchFocus?: () => void;
}

const ICON_MAP: Record<string, React.ElementType> = {
  Scale,
  ShieldAlert,
  Building2,
  KeyRound,
  ShieldCheck,
  HeartHandshake,
  Banknote,
};

export function Navbar({ activeCategory, onSelectCategory, onSearchFocus }: NavbarProps) {
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown on click outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownOpen(false);
      }
    }
    if (dropdownOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [dropdownOpen]);

  const handleCategorySelect = (category: LegalCategory) => {
    onSelectCategory(category);
    setDropdownOpen(false);
    setMobileMenuOpen(false);
  };

  const activeCategoryInfo = CATEGORIES.find((c) => c.id === activeCategory);

  return (
    <header className="sticky top-0 z-50 border-b border-border bg-surface/95 glass-nav shadow-xs">
      <div className="mx-auto flex h-16 max-w-[1380px] items-center justify-between gap-4 px-4 sm:px-6">
        {/* Brand / Logo */}
        <div className="flex items-center gap-6">
          <a
            href="/"
            onClick={(e) => {
              e.preventDefault();
              onSelectCategory("All");
            }}
            className="group flex items-center gap-2.5 transition-opacity hover:opacity-90"
          >
            <div className="flex size-9 items-center justify-center rounded-lg bg-navy text-primary-foreground shadow-sm group-hover:bg-navy/90 transition-colors">
              <Scale className="size-5 text-saffron" aria-hidden="true" />
            </div>
            <div className="leading-tight">
              <div className="flex items-center gap-1.5">
                <span className="font-serif text-[17.5px] font-bold tracking-tight text-navy">
                  Nyayalens
                </span>
                <span className="hidden sm:inline-block rounded bg-navy/5 px-1.5 py-0.5 text-[10px] font-semibold text-brand-blue uppercase tracking-wider">
                  Prototype
                </span>
              </div>
              <p className="text-[11px] font-medium text-muted-foreground">
                Local Precedent Retrieval & Analysis
              </p>
            </div>
          </a>

          {/* Desktop Navigation Links */}
          <nav className="hidden md:flex items-center gap-1">
            {/* Categories Dropdown Trigger */}
            <div className="relative" ref={dropdownRef}>
              <button
                type="button"
                onClick={() => setDropdownOpen((prev) => !prev)}
                aria-expanded={dropdownOpen}
                aria-haspopup="true"
                className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-[13.5px] font-medium transition-all ${
                  dropdownOpen || activeCategory !== "All"
                    ? "bg-navy/8 text-navy font-semibold"
                    : "text-foreground/80 hover:bg-accent hover:text-navy"
                }`}
              >
                <Layers className="size-4 text-brand-blue" />
                <span>
                  {activeCategory === "All"
                    ? "Categories"
                    : activeCategoryInfo?.shortLabel || "Categories"}
                </span>
                <ChevronDown
                  className={`size-3.5 text-muted-foreground transition-transform duration-200 ${
                    dropdownOpen ? "rotate-180 text-navy" : ""
                  }`}
                />
              </button>

              {/* Categories Dropdown Menu */}
              {dropdownOpen && (
                <div className="absolute left-0 top-full mt-2 w-80 rounded-xl border border-border bg-surface p-2 animate-in fade-in-0 zoom-in-95 duration-150 z-50">
                  <div className="px-3 py-2 border-b border-border/60 mb-1">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                      Browse by Legal Category
                    </p>
                    <p className="text-[11.5px] text-muted-foreground/80 mt-0.5">
                      Apply a query template for a legal domain
                    </p>
                  </div>

                  <div className="max-h-[380px] overflow-y-auto space-y-1 py-1">
                    {CATEGORIES.map((cat) => {
                      const Icon = ICON_MAP[cat.iconName] || Scale;
                      const isActive = activeCategory === cat.id;

                      return (
                        <button
                          key={cat.id}
                          type="button"
                          onClick={() => handleCategorySelect(cat.id)}
                          className={`w-full flex items-start gap-3 rounded-lg px-3 py-2.5 text-left transition-colors ${
                            isActive
                              ? "bg-navy text-primary-foreground"
                              : "text-foreground hover:bg-navy/5"
                          }`}
                        >
                          <div
                            className={`flex flex-col items-center justify-center p-2 rounded-lg transition-colors ${
                              isActive
                                ? "bg-foreground/15 text-saffron"
                                : "bg-muted text-brand-blue"
                            }`}
                          >
                            <Icon className="size-4" />
                          </div>

                          <div className="min-w-0 flex-1">
                            <div className="flex items-center justify-between gap-1">
                              <span
                                className={`font-medium ${
                                  isActive ? "text-foreground" : "text-navy"
                                }`}
                              >
                                {cat.label}
                              </span>
                              {isActive && <Check className="size-3.5 text-saffron shrink-0" />}
                            </div>
                            <p
                              className={`text-[11px] ${
                                isActive ? "text-foreground/80" : "text-muted-foreground"
                              }`}
                            >
                              {cat.description}
                            </p>
                          </div>
                        </button>
                      );
                    })}
                  </div>

                  {activeCategory !== "All" && (
                    <div className="mt-1 pt-1.5 border-t border-border/60">
                      <button
                        type="button"
                        onClick={() => handleCategorySelect("All")}
                        className="w-full text-center py-1.5 text-[12px] font-medium text-brand-blue hover:text-navy hover:underline"
                      >
                        Reset to All Categories
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          </nav>
        </div>

        {/* Right Actions (Status pill & Search Jump) */}
        <div className="flex items-center gap-3">
          {onSearchFocus && (
            <button
              type="button"
              onClick={onSearchFocus}
              className="hidden sm:inline-flex items-center gap-2 rounded-lg bg-navy px-3.5 py-2 text-[13px] font-medium text-primary-foreground hover:bg-navy/90 transition-colors"
            >
              <Search className="size-3.5 text-saffron" />
              <span>Describe Case</span>
            </button>
          )}

          <ModeToggle />

          {/* Mobile hamburger toggle */}
          <button
            type="button"
            onClick={() => setMobileMenuOpen((prev) => !prev)}
            aria-expanded={mobileMenuOpen}
            aria-label="Toggle menu"
            className="inline-flex size-9 items-center justify-center rounded-lg border border-border bg-surface text-navy hover:bg-accent md:hidden"
          >
            {mobileMenuOpen ? <X className="size-5" /> : <Menu className="size-5" />}
          </button>
        </div>
      </div>

      {/* Mobile Drawer Menu */}
      {mobileMenuOpen && (
        <div className="border-t border-border bg-surface px-4 py-4 md:hidden animate-in slide-in-from-top-2 duration-200">
          <div className="space-y-4">
            {/* Quick action buttons */}
            <div className="grid grid-cols-1 gap-2">
              <button
                type="button"
                onClick={() => {
                  setMobileMenuOpen(false);
                  if (onSearchFocus) onSearchFocus();
                }}
                className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-navy p-2.5 text-[13px] font-medium text-primary-foreground"
              >
                <Search className="size-4 text-saffron" />
                <span>Search Cases</span>
              </button>
            </div>

            {/* Categories list in Mobile */}
            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-[12px] font-semibold text-navy uppercase tracking-wider">
                  Select Legal Category
                </span>
                {activeCategory !== "All" && (
                  <button
                    type="button"
                    onClick={() => handleCategorySelect("All")}
                    className="text-[11.5px] font-medium text-brand-blue"
                  >
                    Reset
                  </button>
                )}
              </div>

              <div className="grid grid-cols-1 gap-1.5">
                {CATEGORIES.map((cat) => {
                  const Icon = ICON_MAP[cat.iconName] || Scale;
                  const isActive = activeCategory === cat.id;

                  return (
                    <button
                      key={cat.id}
                      type="button"
                      onClick={() => handleCategorySelect(cat.id)}
                      className={`flex items-center justify-between rounded-lg px-3.5 py-2.5 text-left text-[13px] transition-colors ${
                        isActive
                          ? "bg-navy font-semibold text-primary-foreground"
                          : "bg-background text-foreground hover:bg-accent"
                      }`}
                    >
                      <div className="flex items-center gap-2.5">
                        <Icon
                          className={`size-4 ${isActive ? "text-saffron" : "text-brand-blue"}`}
                        />
                        <span>{cat.label}</span>
                      </div>
                      {isActive && (
                        <span className="rounded bg-saffron px-1.5 py-0.5 text-[10px] font-bold text-navy uppercase">
                          Selected
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
