export interface ReplayStep {
  stage: string;
  detail: string;
  timestamp: string;
}

export interface ReplayRecord {
  id: string;
  project: string;
  title: string;
  createdAt: string;
  steps: ReplayStep[];
  readOnly: true;
}

export interface ReplayListResponse {
  replays: ReplayRecord[];
  readOnly: true;
}
