export interface DemoScenarioRecord {
  id: string;
  name: string;
  issue: string;
  stages: string[];
  createdAt?: string;
  readOnly: true;
}

export interface DemoCatalogResponse {
  scenarios: DemoScenarioRecord[];
  readOnly: true;
}

export interface DemoFlowResponse {
  flow: string[];
  readOnly: true;
}
