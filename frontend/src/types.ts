export type Metric = {
  value: number | null;
  method: string;
  source: string;
  sample: number;
  available: boolean;
  period: number;
  updated: number;
};
export type Metrics = Record<string, Metric>;
export type Match = {
  id: string;
  started: number;
  finished: number;
  won: number | null;
  complete: number;
  maps: ({ map: string } & Record<string, number | null | string>)[];
};
export type Insight = {
  id: string;
  title: string;
  rule: string;
  count: number;
  sample: number;
  label: string;
  source: string;
  skill: string;
  exercise: string;
  criterion: string;
  minutes: number;
  reassess: string;
  confidence: string;
  impact: string;
  at: number;
  evidence: {
    match?: string;
    demo?: string;
    round?: number;
    tick?: number;
    adr?: number;
  }[];
};
export type Options = {
  sync_minutes: number;
  session_gap: number;
  minutes: number;
  watch: string;
  steam_id: string;
  paused: boolean;
  notifications: boolean;
  ai_base: string;
  model: string;
  autostart: boolean;
};
export type Exercise = {
  id: number;
  day: string;
  kind: string;
  skill: string;
  instruction: string;
  minutes: number;
  completed: number | null;
  difficulty: number | null;
};
export type Session = {
  observations: string[];
  elo_delta: number | null;
  id: string;
  started: number;
  finished: number;
  matches: string[];
  metrics: Metrics;
  best: string | null;
  worst: string | null;
  diary: Record<string, string | number | null>;
  trend: [string, number | null][];
};
export type State = {
  options: Options;
  keys: { faceit: boolean; ai: boolean };
  goal: {
    current: number | null;
    target: number;
    peak: number | null;
    remaining: number | null;
    next: number | null;
    week: number | null;
    month: number | null;
    history: { at: number; elo: number }[];
  };
  analytics: {
    metrics: Metrics;
    previous: Metrics;
    delta: Record<string, number | null>;
    count: number;
    maps: Record<string, Metrics>;
  };
  matches: Match[];
  sessions: Session[];
  evaluations: {
    id: string;
    title: string;
    before: number | null;
    current: number | null;
    unit: string;
    completed: number;
    sample: number;
    ready: boolean;
  }[];
  insights: Insight[];
  history: Insight[];
  ranking: string;
  training: {
    exercises: Exercise[];
    skills: string[];
    kinds: string[];
    progress: number | null;
  };
  demos: {
    match_id: string | null;
    id: string;
    name: string;
    status: string;
    progress: number;
    error: string | null;
    version: string;
  }[];
  reports: { id: string; title: string; at: number }[];
  jobs: { id: number; kind: string; state: string; message: string }[];
  root: string;
};
export type EventRow = {
  kind: string;
  tick: number;
  user_name?: string;
  attacker_name?: string;
  weapon?: string;
} & Record<string, unknown>;
export type DemoDetail = {
  match_id: string | null;
  name: string;
  summary: {
    map?: string;
    player?: string;
    players?: Record<string, string>;
    metrics?: Record<string, number>;
    weapons?: Record<string, Record<string, number>>;
    sides?: Record<string, Record<string, number>>;
    distances?: Record<string, Record<string, number>>;
    repeated_zones?: Record<string, number>;
    grenades?: unknown[];
    utility?: Record<string, Record<string, number>>;
    metric_records?: Metrics;
    supported?: string[];
    version?: string;
  };
  rounds: {
    number: number;
    start: number;
    end: number;
    side: string | null;
    winner: string | null;
    metrics: Record<string, number>;
    roster: unknown[];
    duels: unknown[];
    hypotheses?: { tick: number; label: string }[];
    facts: { tick: number; label: string }[];
  }[];
};
