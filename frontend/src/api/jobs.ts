import type {
  ApiErrorResponse,
  Job,
  JobListResponse,
  JobState,
  JobSubmitRequest,
} from "../features/jobs/types";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api";

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

export function submitJob(submission: JobSubmitRequest): Promise<Job> {
  return request<Job>("/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(submission),
  });
}
