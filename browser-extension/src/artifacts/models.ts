export interface ArtifactRecord {
  id: string;
  kind: string;
  project: string;
  createdAt: string;
  payload: Record<string, unknown>;
  markdown: string;
  readOnly: true;
}

export interface ArtifactListResponse {
  artifacts: ArtifactRecord[];
  readOnly: true;
}
