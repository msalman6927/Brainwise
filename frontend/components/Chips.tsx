import type { Difficulty, Level, Phase } from "@/lib/types";

const LEVEL_STYLES: Record<Level, string> = {
  Foundation: "border-amber-200 bg-amber-100 text-amber-900",
  Basic: "border-green-200 bg-green-100 text-green-900",
  Intermediate: "border-blue-200 bg-blue-100 text-blue-900",
  Advanced: "border-purple-200 bg-purple-100 text-purple-900",
};

const LEVEL_DOT: Record<Level, string> = {
  Foundation: "bg-level-foundation",
  Basic: "bg-level-basic",
  Intermediate: "bg-level-intermediate",
  Advanced: "bg-level-advanced",
};

export function LevelBadge({ level, size = "sm" }: { level: Level; size?: "sm" | "lg" }) {
  const lg = size === "lg";
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border font-semibold ${
        lg ? "px-4 py-1.5 text-lg" : "px-2 py-0.5 text-xs"
      } ${LEVEL_STYLES[level]}`}
    >
      <span aria-hidden="true" className={`rounded-full ${lg ? "size-2.5" : "size-1.5"} ${LEVEL_DOT[level]}`} />
      {level}
    </span>
  );
}

export function IqChip({ iq }: { iq: number }) {
  return (
    <span className="inline-flex items-center rounded-full border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-xs font-semibold text-indigo-800">
      IQ {iq}
    </span>
  );
}

const PHASE_LABEL: Record<Phase, string | null> = {
  idle: null,
  topic_set: "New",
  assessing: "Assessing",
  scoring: "Scoring",
  explaining: "Explaining",
  follow_up: "In conversation",
};

const PHASE_STYLE: Partial<Record<Phase, string>> = {
  topic_set: "border-slate-200 bg-slate-100 text-slate-700",
  assessing: "border-amber-200 bg-amber-100 text-amber-900",
  scoring: "border-amber-200 bg-amber-100 text-amber-900",
  explaining: "border-sky-200 bg-sky-100 text-sky-900",
  follow_up: "border-green-200 bg-green-100 text-green-900",
};

export function PhaseChip({ phase }: { phase: Phase }) {
  const label = PHASE_LABEL[phase];
  if (!label) return null;
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${PHASE_STYLE[phase] ?? "border-border bg-background text-muted"}`}
    >
      {label}
    </span>
  );
}

const DIFFICULTY_STYLE: Record<Difficulty, string> = {
  easy: "border-green-200 bg-green-50 text-green-800",
  medium: "border-amber-200 bg-amber-50 text-amber-800",
  hard: "border-red-200 bg-red-50 text-red-800",
};

export function DifficultyBadge({ difficulty }: { difficulty: Difficulty }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold capitalize ${DIFFICULTY_STYLE[difficulty]}`}
    >
      {difficulty}
    </span>
  );
}
