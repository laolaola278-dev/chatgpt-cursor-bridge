export interface ProjectProfile {
  projectId: string;
  languages: Record<string, number>;
  frameworks: string[];
  architectureSummary: string;
  moduleCount: number;
  complexityScore: number;
  readOnly: true;
}

export interface ProjectGraphNode {
  id: string;
  type: string;
  label: string;
  metadata: Record<string, unknown>;
}

export interface ProjectGraphEdge {
  source: string;
  target: string;
  relation: string;
}

export interface ProjectGraphResponse {
  project: string;
  nodes: ProjectGraphNode[];
  edges: ProjectGraphEdge[];
  readOnly: true;
}

export interface ImpactReport {
  project: string;
  changedFiles: string[];
  affectedModules: string[];
  risk: string;
  readOnly: true;
}

export interface ProjectMemoryHistoryResponse {
  project: string;
  history: Array<{
    category: string;
    path: string;
    updatedAt: string;
    size: number;
  }>;
  readOnly: true;
}
