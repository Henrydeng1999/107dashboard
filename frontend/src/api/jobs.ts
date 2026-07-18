import type {
  ApiErrorResponse,
  Job,
  JobLogResponse,
  JobLogStream,
  JobListResponse,
  JobState,
  JobSubmitRequest,
  JobUsageResponse,
  RuntimeInfo,
  TestProjectListResponse,
  UserJobSummary,
} from "../features/jobs/types";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL
  ?? (import.meta.env.DEV ? "http://127.0.0.1:8000/api" : "/api");

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly requestId?: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, options);
  if (response.ok) {
    return (await response.json()) as T;
  }

  let payload: ApiErrorResponse = {};
  try {
    payload = (await response.json()) as ApiErrorResponse;
  } catch {
    // The fallback below keeps server internals out of the interface.
  }
  throw new ApiError(
    payload.error?.message ?? "作业数据暂时不可用",
    response.status,
    payload.error?.request_id,
  );
}

export function fetchJobs(
  page: number,
  pageSize: number,
  state: JobState | "ALL",
  signal?: AbortSignal,
): Promise<JobListResponse> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (state !== "ALL") {
    params.set("state", state);
  }
  return request<JobListResponse>(`/jobs?${params.toString()}`, { signal });
}

export function fetchJob(jobId: string, signal?: AbortSignal): Promise<Job> {
  return request<Job>(`/jobs/${encodeURIComponent(jobId)}`, { signal });
}

export function submitJob(submission: JobSubmitRequest, idempotencyKey: string): Promise<Job> {
  return request<Job>("/jobs", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify(submission),
  });
}

export function cancelJob(jobId: string, idempotencyKey: string): Promise<Job> {
  return request<Job>(`/jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
  });
}

export function cloneJob(jobId: string, idempotencyKey: string): Promise<Job> {
  return request<Job>(`/jobs/${encodeURIComponent(jobId)}/clone`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
  });
}

export function fetchJobLog(
  jobId: string,
  stream: JobLogStream,
  offset = 0,
  signal?: AbortSignal,
): Promise<JobLogResponse> {
  const params = new URLSearchParams({ stream, offset: String(offset) });
  return request<JobLogResponse>(`/jobs/${encodeURIComponent(jobId)}/logs?${params}`, { signal });
}

export function fetchJobUsage(jobId: string, signal?: AbortSignal): Promise<JobUsageResponse> {
  return request<JobUsageResponse>(`/jobs/${encodeURIComponent(jobId)}/usage`, { signal });
}

export function fetchJobSummary(signal?: AbortSignal): Promise<UserJobSummary> {
  return request<UserJobSummary>("/jobs/summary", { signal });
}

export function fetchRuntimeInfo(signal?: AbortSignal): Promise<RuntimeInfo> {
  return request<RuntimeInfo>("/runtime", { signal });
}

export function fetchTestProjects(signal?: AbortSignal): Promise<TestProjectListResponse> {
  return request<TestProjectListResponse>("/projects", { signal });
}
