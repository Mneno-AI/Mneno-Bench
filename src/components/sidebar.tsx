import {
  BarChart3,
  FlaskConical,
  GitCompareArrows,
  History,
  Landmark,
  MemoryStick,
} from "lucide-react";

export type PageKey = "dashboard" | "runs" | "compare" | "mneno-suite" | "locomo";

interface SidebarProps {
  activePage: PageKey;
  onNavigate: (page: PageKey) => void;
}

const navigation = [
  { id: "dashboard" as const, label: "Dashboard", icon: BarChart3 },
  { id: "runs" as const, label: "Runs", icon: History },
  { id: "compare" as const, label: "Compare", icon: GitCompareArrows },
  { id: "mneno-suite" as const, label: "Mneno Suite", icon: FlaskConical },
  { id: "locomo" as const, label: "LOCOMO", icon: Landmark },
];

export function Sidebar({ activePage, onNavigate }: SidebarProps) {
  return (
    <>
      <header className="fixed inset-x-0 top-0 z-40 flex h-16 items-center border-b border-ink-950/10 bg-white px-4 lg:hidden">
        <Brand />
        <nav aria-label="Primary" className="ml-auto flex items-center gap-1">
          {navigation.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                type="button"
                aria-label={item.label}
                aria-current={activePage === item.id ? "page" : undefined}
                title={item.label}
                onClick={() => onNavigate(item.id)}
                className={`flex size-11 cursor-pointer items-center justify-center rounded-md transition-colors ${
                  activePage === item.id
                    ? "bg-signal-100 text-signal-700"
                    : "text-ink-600 hover:bg-canvas hover:text-ink-950"
                }`}
              >
                <Icon aria-hidden="true" size={20} />
              </button>
            );
          })}
        </nav>
      </header>

      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 border-r border-ink-950/10 bg-white px-4 py-6 lg:block">
        <Brand />
        <nav aria-label="Primary" className="mt-10 space-y-1">
          {navigation.map((item) => {
            const Icon = item.icon;
            const active = activePage === item.id;
            return (
              <button
                key={item.id}
                type="button"
                aria-current={active ? "page" : undefined}
                onClick={() => onNavigate(item.id)}
                className={`flex min-h-11 w-full cursor-pointer items-center gap-3 rounded-md px-3 text-left text-sm font-medium transition-colors ${
                  active
                    ? "bg-signal-100 text-signal-700"
                    : "text-ink-600 hover:bg-canvas hover:text-ink-950"
                }`}
              >
                <Icon aria-hidden="true" size={19} />
                {item.label}
              </button>
            );
          })}
        </nav>
        <div className="absolute bottom-6 left-4 right-4 border-t border-ink-950/10 pt-4">
          <p className="font-mono text-xs text-ink-600">STEP 5 / LOCOMO</p>
          <p className="mt-1 text-xs leading-5 text-ink-600">
            External dataset optional. Mneno remains optional.
          </p>
        </div>
      </aside>
    </>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-3">
      <span className="flex size-9 items-center justify-center rounded-md bg-ink-950 text-white">
        <MemoryStick aria-hidden="true" size={20} />
      </span>
      <div>
        <p className="text-sm font-semibold leading-4">Mneno Bench</p>
        <p className="font-mono text-[11px] leading-4 text-ink-600">v0.5 locomo</p>
      </div>
    </div>
  );
}
