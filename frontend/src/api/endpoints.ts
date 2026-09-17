import { apiClient } from "./client";
import type {
  AgentRun,
  Approval,
  AuthToken,
  ChatMessage,
  CodeChange,
  Conversation,
  DependencyGraph,
  DiffSummary,
  FileContent,
  FileTreeNode,
  Finding,
  PullRequest,
  Repository,
  RepositorySummary,
  SymbolRead,
  Task,
  TestRun,
  User,
} from "./types";

// --- Auth ---
export const authApi = {
  register: (email: string, password: string, full_name?: string) =>
    apiClient.post<AuthToken>("/auth/register", { email, password, full_name }).then((r) => r.data),
  login: (email: string, password: string) =>
    apiClient.post<AuthToken>("/auth/login", { email, password }).then((r) => r.data),
  me: () => apiClient.get<User>("/auth/me").then((r) => r.data),
};

// --- Repositories ---
export const repositoryApi = {
  list: () => apiClient.get<Repository[]>("/repositories").then((r) => r.data),
  get: (id: string) => apiClient.get<Repository>(`/repositories/${id}`).then((r) => r.data),
  createFromGithub: (repo_url: string, name?: string, branch?: string) =>
    apiClient.post<Repository>("/repositories/github", { repo_url, name, branch }).then((r) => r.data),
  uploadZip: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiClient
      .post<Repository>("/repositories/upload", form, { headers: { "Content-Type": "multipart/form-data" } })
      .then((r) => r.data);
  },
  progress: (id: string) => apiClient.get(`/repositories/${id}/progress`).then((r) => r.data),
  summary: (id: string) => apiClient.get<RepositorySummary>(`/repositories/${id}/summary`).then((r) => r.data),
  rescan: (id: string) => apiClient.post<Repository>(`/repositories/${id}/rescan`).then((r) => r.data),
  remove: (id: string) => apiClient.delete(`/repositories/${id}`),
};

// --- Files / Explorer ---
export const filesApi = {
  tree: (repoId: string) => apiClient.get<FileTreeNode[]>(`/repositories/${repoId}/files/tree`).then((r) => r.data),
  content: (repoId: string, path: string) =>
    apiClient.get<FileContent>(`/repositories/${repoId}/files/content`, { params: { path } }).then((r) => r.data),
  symbols: (repoId: string, path: string) =>
    apiClient.get<SymbolRead[]>(`/repositories/${repoId}/files/symbols`, { params: { path } }).then((r) => r.data),
  searchSymbols: (repoId: string, q: string) =>
    apiClient.get<SymbolRead[]>(`/repositories/${repoId}/symbols/search`, { params: { q } }).then((r) => r.data),
  searchCode: (repoId: string, q: string, language?: string) =>
    apiClient
      .get(`/repositories/${repoId}/search`, { params: { q, language } })
      .then((r) => r.data),
  dependencyGraph: (repoId: string) =>
    apiClient.get<DependencyGraph>(`/repositories/${repoId}/dependency-graph`).then((r) => r.data),
};

// --- Chat ---
export const chatApi = {
  listConversations: (repoId: string) =>
    apiClient.get<Conversation[]>(`/repositories/${repoId}/conversations`).then((r) => r.data),
  getConversation: (repoId: string, conversationId: string) =>
    apiClient.get<Conversation>(`/repositories/${repoId}/conversations/${conversationId}`).then((r) => r.data),
  send: (repoId: string, message: string, conversationId?: string) =>
    apiClient
      .post<ChatMessage>(`/repositories/${repoId}/chat`, { message, conversation_id: conversationId })
      .then((r) => r.data),
};

// --- Tasks / Debugging ---
export const taskApi = {
  startDebug: (
    repoId: string,
    description: string,
    error_message?: string,
    stack_trace?: string,
    logs?: string,
    failing_test?: string
  ) =>
    apiClient
      .post<Task>(`/repositories/${repoId}/debug`, { description, error_message, stack_trace, logs, failing_test })
      .then((r) => r.data),
  list: (repoId: string) => apiClient.get<Task[]>(`/repositories/${repoId}/tasks`).then((r) => r.data),
  get: (repoId: string, taskId: string) =>
    apiClient.get<Task>(`/repositories/${repoId}/tasks/${taskId}`).then((r) => r.data),
  startFix: (repoId: string, taskId: string) =>
    apiClient.post<Task>(`/repositories/${repoId}/tasks/${taskId}/fix`).then((r) => r.data),
};

// --- Code changes / diff ---
export const changesApi = {
  list: (repoId: string, taskId: string) =>
    apiClient.get<CodeChange[]>(`/repositories/${repoId}/tasks/${taskId}/changes`).then((r) => r.data),
  diff: (repoId: string, taskId: string) =>
    apiClient.get<DiffSummary>(`/repositories/${repoId}/tasks/${taskId}/diff`).then((r) => r.data),
};

// --- Tests ---
export const testsApi = {
  forTask: (repoId: string, taskId: string) =>
    apiClient.get<TestRun[]>(`/repositories/${repoId}/tasks/${taskId}/test-runs`).then((r) => r.data),
  forRepository: (repoId: string) => apiClient.get<TestRun[]>(`/repositories/${repoId}/test-runs`).then((r) => r.data),
};

// --- Security findings ---
export const findingsApi = {
  list: (repoId: string) => apiClient.get<Finding[]>(`/repositories/${repoId}/findings`).then((r) => r.data),
  triggerScan: (repoId: string) => apiClient.post(`/repositories/${repoId}/findings/scan`),
  updateStatus: (repoId: string, findingId: string, status: string) =>
    apiClient.patch<Finding>(`/repositories/${repoId}/findings/${findingId}`, { status }).then((r) => r.data),
};

// --- Approvals ---
export const approvalsApi = {
  list: (repoId: string, taskId?: string) =>
    apiClient.get<Approval[]>(`/repositories/${repoId}/approvals`, { params: { task_id: taskId } }).then((r) => r.data),
  decide: (repoId: string, approvalId: string, status: "APPROVED" | "REJECTED" | "CHANGES_REQUESTED", comment?: string) =>
    apiClient.patch<Approval>(`/repositories/${repoId}/approvals/${approvalId}`, { status, comment }).then((r) => r.data),
};

// --- Agent runs / observability ---
export const agentRunsApi = {
  list: (repoId: string, taskId?: string) =>
    apiClient.get<AgentRun[]>(`/repositories/${repoId}/agent-runs`, { params: { task_id: taskId } }).then((r) => r.data),
  get: (repoId: string, runId: string) =>
    apiClient.get<AgentRun>(`/repositories/${repoId}/agent-runs/${runId}`).then((r) => r.data),
};

// --- Git / PR ---
export const gitApi = {
  createBranch: (repoId: string, taskId: string, branchName?: string) =>
    apiClient
      .post<PullRequest>(`/repositories/${repoId}/tasks/${taskId}/git/branch`, { branch_name: branchName })
      .then((r) => r.data),
  listPullRequests: (repoId: string, taskId: string) =>
    apiClient.get<PullRequest[]>(`/repositories/${repoId}/tasks/${taskId}/pull-requests`).then((r) => r.data),
  openPullRequest: (repoId: string, taskId: string, title?: string, description?: string) =>
    apiClient
      .post<PullRequest>(`/repositories/${repoId}/tasks/${taskId}/git/pull-request`, { title, description, open_pr: true })
      .then((r) => r.data),
};
