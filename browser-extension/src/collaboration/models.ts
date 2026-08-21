export type AgentTeamStatus = "CREATED" | "PLANNING" | "EXECUTING" | "WAITING_APPROVAL" | "REVIEWING" | "COMPLETED" | "FAILED";

export interface AgentTeamRecord {
  id: string;
  workflowId: string;
  members: string[];
  leader: string;
  status: AgentTeamStatus;
  createdAt: string;
  updatedAt: string;
}

export interface TaskDependencyRecord {
  sourceTask: string;
  targetTask: string;
  dependencyType: string;
}

export interface CollaborationEventRecord {
  messageId: string;
  type: string;
  sender: string;
  receiver: string;
  taskId: string;
  workflowId: string;
  context: string;
  timestamp: string;
}

export interface TeamListResponse { teams: AgentTeamRecord[] }
export interface TaskDependenciesResponse { taskId: string; dependencies: TaskDependencyRecord[]; hasCycle: boolean }
export interface CollaborationEventsResponse { events: CollaborationEventRecord[] }
