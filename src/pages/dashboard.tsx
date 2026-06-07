import { Dashboard } from "../components/dashboard";
import type { PageKey } from "../components/sidebar";

export function DashboardPage({
  onNavigate,
}: {
  onNavigate: (page: PageKey) => void;
}) {
  return (
    <>
      <PageHeader
        eyebrow="Mneno-first evaluation"
        title="Context integrity, measured."
        description="Step 1 validates whether Mneno can outperform simple context baselines before public benchmark claims are introduced."
      />
      <Dashboard onNavigate={onNavigate} />
    </>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <header className="mb-8 max-w-3xl">
      <p className="font-mono text-xs font-medium uppercase text-signal-700">
        {eyebrow}
      </p>
      <h1 className="mt-2 text-3xl font-semibold sm:text-4xl">{title}</h1>
      <p className="mt-3 max-w-2xl text-base leading-7 text-ink-600">{description}</p>
    </header>
  );
}
