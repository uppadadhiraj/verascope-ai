export interface User {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
}

export interface AuthToken {
  access_token: string;
  token_type: string;
  user: User;
}

export type RepositoryStatus =
  | "PENDING"
  | "CLONING"
  | "SCANNING"
  | "PARSING"
  | "EMBEDDING"
  | "SUMMARIZING"
  | "READY"
  | "FAILED";

export interface Repository {
  id: string;
  name: string;
  source_type: "GITHUB" | "ZIP";
  source_url: string | null;
  default_branch: string;
  status: RepositoryStatus;
  status_detail: string | null;
  error_message: string | null;
  languages: Record<string, number> | null;
  frameworks: string[] | null;
  file_count: number;
  total_size_bytes: number;
  last_indexed_at: string | null;
  last_security_scan_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RepositorySummary {
  purpose: string | null;
  languages: string[];
  frameworks: string[];
  important_directories: string[];
  entry_points: string[];
  api_entry_points: string[];
  database: string | null;
  authentication: string | null;
  major_components: string[];
  test_framework: string | null;
  build_instructions: string | null;
  important_config_files: string[];
  facts: string[];
  inferences: string[];
  uncertain: string[];
}

export interface FileTreeNode {
  name: string;
  path: string;
  type: "file" | "directory";
  language: string | null;
  children: FileTreeNode[];
}

export interface FileContent {
  path: string;
  language: string | null;
  content: string;
  line_count: number;
}

export interface DependencyGraphNode {
  id: string;
  language: string | null;
  is_test: boolean;
  in_degree: number;
  out_degree: number;
}

export interface DependencyGraphEdge {
  source: string;
  target: string;
  relationship: string;
}

export interface DependencyGraph {
  nodes: DependencyGraphNode[];
  edges: DependencyGraphEdge[];
  truncated: boolean;
}

export interface SymbolRead {
  id: string;
  file_id: string;
  name: string;
  symbol_type: string;
  language: string;
  start_line: number;
  end_line: number;
  signature: string | null;
  docstring: string | null;
  route_path: string | null;
  http_method: string | null;
}

export interface CodeSearchResult {
  file_path: string;
  start_line: number;
  end_line: number;
  symbol: string | null;
  chunk_type: string;
  content: string;
  score: number;
}

export interface Citation {
  file_path: string;
  start_line: number | null;
  end_line: number | null;
  symbol: string | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  citations: Citation[] | null;
  token_usage: Record<string, unknown> | null;
  created_at: string;
}

export interface Conversation {
  id: string;
  repository_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages?: ChatMessage[];
}

export type StepStatus = "PENDING" | "IN_PROGRESS" | "COMPLETED" | "FAILED" | "BLOCKED";
export type EvidenceStatus = "OBSERVED" | "INFERRED" | "HYPOTHESIZED" | "VERIFIED" | "INSUFFICIENT";

export interface TaskStep {
  id: string;
  step_number: number;
  description: string;
  status: StepStatus;
  evidence: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface Task {
  id: string;
  repository_id: string;
  title: string;
  description: string | null;
  task_type: "CHAT" | "DEBUG" | "FEATURE" | "SECURITY_SCAN" | "GENERAL";
  status: StepStatus;
  root_cause: string | null;
  evidence: Array<{ file_path: string; start_line?: number; end_line?: number; note?: string }> | null;
  evidence_status: EvidenceStatus | null;
  confidence_notes: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  steps?: TaskStep[];
}

export type ApprovalType = "CODE_CHANGE" | "GIT_OPERATION" | "PR_CREATION";
export type ApprovalStatus = "PENDING" | "APPROVED" | "REJECTED" | "CHANGES_REQUESTED";

export interface Approval {
  id: string;
  task_id: string;
  approval_type: ApprovalType;
  status: ApprovalStatus;
  summary_snapshot: Record<string, any>;
  comment: string | null;
  decided_at: string | null;
  created_at: string;
}

export type ChangeType = "CREATE" | "MODIFY" | "DELETE";
export type ChangeLifecycleState = "PROPOSED" | "APPLIED" | "TESTED" | "VALIDATED" | "REJECTED";

export interface CodeChange {
  id: string;
  task_id: string;
  change_type: ChangeType;
  lifecycle_state: ChangeLifecycleState;
  file_path: string;
  diff: string | null;
  reason: string;
  agent_name: string;
  applied_to_main: boolean;
  created_at: string;
}

export interface DiffSummary {
  task_id: string;
  files_created: string[];
  files_modified: string[];
  files_deleted: string[];
  changes: CodeChange[];
  unified_diff: string;
}

export type TestRunStatus = "PASSED" | "FAILED" | "ERROR" | "TIMEOUT";

export interface TestRun {
  id: string;
  task_id: string | null;
  framework: string | null;
  command: string;
  exit_code: number | null;
  duration_ms: number | null;
  passed_count: number | null;
  failed_count: number | null;
  output: string | null;
  error_output: string | null;
  status: TestRunStatus;
  iteration: number;
  created_at: string;
}

export type FindingSeverity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type FindingStatus = "OPEN" | "ACKNOWLEDGED" | "RESOLVED" | "FALSE_POSITIVE";

export interface Finding {
  id: string;
  finding_type: string;
  severity: FindingSeverity;
  status: FindingStatus;
  file_path: string;
  start_line: number | null;
  end_line: number | null;
  evidence: string;
  explanation: string;
  impact: string | null;
  remediation: string | null;
  created_at: string;
}

export type AgentName =
  | "orchestrator"
  | "planner"
  | "repository"
  | "debugger"
  | "security"
  | "test"
  | "fix"
  | "review"
  | "validation";

export type AgentRunStatus = "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";

export interface ToolCall {
  id: string;
  tool_name: string;
  arguments: Record<string, unknown> | null;
  result_summary: string | null;
  status: string;
  error_message: string | null;
  duration_ms: number | null;
  created_at: string;
}

export interface AgentRun {
  id: string;
  repository_id: string;
  task_id: string | null;
  agent_name: AgentName;
  status: AgentRunStatus;
  started_at: string;
  ended_at: string | null;
  input_summary: string | null;
  output_summary: string | null;
  error_message: string | null;
  files_accessed: string[] | null;
  files_modified: string[] | null;
  model: string | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  latency_ms: number | null;
  tool_calls?: ToolCall[];
}

export type PullRequestStatus =
  | "DRAFT"
  | "BRANCH_CREATED"
  | "COMMITTED"
  | "PUSHED"
  | "PR_CREATED"
  | "FAILED";

export interface PullRequest {
  id: string;
  task_id: string;
  branch_name: string;
  base_branch: string;
  commit_sha: string | null;
  pr_number: number | null;
  pr_url: string | null;
  title: string;
  description: string | null;
  status: PullRequestStatus;
  error_message: string | null;
  created_at: string;
}
