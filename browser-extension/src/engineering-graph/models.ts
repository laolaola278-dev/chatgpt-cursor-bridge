export interface EngineeringGraphNode {
  id: string;
  type: string;
  project: string;
  label: string;
  metadata: Record<string, unknown>;
  createdAt: string;
}

export interface EngineeringGraphEdge {
  source: string;
  target: string;
  relation: string;
  project: string;
  metadata: Record<string, unknown>;
  createdAt: string;
}

export interface EngineeringGraphResponse {
  project: string;
  nodes: EngineeringGraphNode[];
  edges: EngineeringGraphEdge[];
  generatedAt?: string;
  readOnly: true;
}

export interface FailurePattern {
  id: string;
  project: string;
  category: string;
  signature: string;
  occurrences: number;
  severity: string;
  evidence: Array<Record<string, unknown>>;
  createdAt: string;
  readOnly: true;
}

export interface FailurePatternsResponse {
  project: string;
  patterns: FailurePattern[];
  readOnly: true;
}

export interface EvolutionTimelineEntry {
  id: string;
  project: string;
  kind: string;
  title: string;
  content: string;
  sourceId: string | null;
  createdAt: string;
  readOnly: true;
}

export interface EvolutionTimelineResponse {
  project: string;
  timeline: EvolutionTimelineEntry[];
  readOnly: true;
}

export interface AgentCapabilityMetric {
  agentId: string;
  tasksCompleted: number;
  failedTasks: number;
  successRate: number;
  reviewScore: number;
  averageQuality: number;
  rollbackRate: number;
  failurePatterns: FailurePattern[];
  readOnly: true;
}

export interface AgentCapabilityMetricsResponse {
  metrics: AgentCapabilityMetric[];
  readOnly: true;
}
