export interface SimulationRecord {
  id: string;
  project: string;
  problem: string;
  status: string;
  createdAt: string;
  updatedAt: string;
  history: Array<{ status: string; at: string }>;
  readOnly: true;
  plans?: EngineeringPlan[];
}

export interface SimulationScenario {
  id: string;
  simulationId: string;
  name: string;
  type: string;
  changes: string[];
  affectedFiles: string[];
  dependentModules: string[];
  affectedTests: string[];
  workflowStages: string[];
  memoryImpacts: string[];
  riskScore: number;
  impactScore: number;
  risk: string;
  status: string;
  readOnly: true;
}

export interface SimulationEvaluation {
  scenario: string;
  score: number;
  risk: string;
  advantages: string[];
  disadvantages: string[];
  factors: Record<string, number>;
  readOnly: true;
}

export interface EngineeringPlan {
  id: string;
  simulationId: string;
  scenarioId: string;
  content: string;
  status: string;
  createdAt: string;
  readOnly: true;
}

export interface SimulationScenariosResponse { simulationId: string; scenarios: SimulationScenario[]; readOnly: true; }
export interface SimulationEvaluationResponse { simulationId: string; evaluations: SimulationEvaluation[]; readOnly: true; }
export interface SimulationPlansResponse { simulationId: string; plans: EngineeringPlan[]; readOnly: true; }
export interface SimulationQuality6 {
  quality: number;
  simulationConfidence: number;
  alternativeCoverage: number;
  riskPredictionAccuracy: number;
  planCompleteness: number;
  missingInformation: string[];
  readOnly: true;
}
