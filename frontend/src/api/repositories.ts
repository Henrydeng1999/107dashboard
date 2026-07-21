import { ApiError } from "./jobs";
import type {
  GitCommitDetail,
  GitRepositoryDetail,
  GitRepositoryList,
} from "../features/repositories/types";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL
  ?? (import.meta.env.DEV ? "http://127.0.0.1:8000/api" : "/api");

async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, { signal });
  if (response.ok) return await response.json() as T;
  let message = "Git 仓库数据暂时不可用";
  try {
    message = (await response.json() as { error?: { message?: string } }).error?.message ?? message;
  } catch {
    // The fallback keeps server details out of the interface.
  }
  throw new ApiError(message, response.status);
}

export function fetchRepositories(signal?: AbortSignal): Promise<GitRepositoryList> {
  return request("/repositories", signal);
}

export function fetchRepository(id: string, signal?: AbortSignal): Promise<GitRepositoryDetail> {
  return request(`/repositories/${encodeURIComponent(id)}`, signal);
}

export function fetchRepositoryCommit(
  repositoryId: string,
  revision: string,
  signal?: AbortSignal,
): Promise<GitCommitDetail> {
  return request(
    `/repositories/${encodeURIComponent(repositoryId)}/commits/${encodeURIComponent(revision)}`,
    signal,
  );
}
