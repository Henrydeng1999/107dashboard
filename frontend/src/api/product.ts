import { ApiError } from "./jobs";
import type { AiCallRecord, AiChatResponse, AiProvider, AiProviderModelList, AiProviderTestResult, DiagnosticReport, EvaluationProject, PromptTemplate } from "../features/product/types";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? "http://127.0.0.1:8000/api" : "/api");

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, options);
  if (response.ok) return await response.json() as T;
  let message = "产品数据暂时不可用";
  try { message = (await response.json() as { error?: { message?: string } }).error?.message ?? message; } catch { /* sanitized fallback */ }
  throw new ApiError(message, response.status);
}

const json = (body: unknown): RequestInit => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export async function fetchReports(signal?: AbortSignal): Promise<DiagnosticReport[]> { return (await request<{ items: DiagnosticReport[] }>("/reports", { signal })).items; }
export async function fetchEvaluationProjects(signal?: AbortSignal): Promise<EvaluationProject[]> { return (await request<{ items: EvaluationProject[] }>("/evaluation-projects", { signal })).items; }
export function createEvaluationProject(payload: { name: string; description: string; job_ids: string[] }): Promise<EvaluationProject> { return request("/evaluation-projects", json(payload)); }
export async function fetchAiProviders(signal?: AbortSignal): Promise<AiProvider[]> { return (await request<{ items: AiProvider[] }>("/ai/providers", { signal })).items; }
export function saveAiProvider(id: string, payload: { name: string; base_url: string; model: string; api_key?: string }): Promise<AiProvider> { return request(`/ai/providers/${encodeURIComponent(id)}`, { ...json(payload), method: "PUT" }); }
export function testAiProvider(id: string): Promise<AiProviderTestResult> { return request(`/ai/providers/${encodeURIComponent(id)}/test`, { method: "POST" }); }
export function fetchAiProviderModels(id: string): Promise<AiProviderModelList> { return request(`/ai/providers/${encodeURIComponent(id)}/models`); }
export function testAiProviderModel(id: string, model: string): Promise<AiProviderTestResult> { return request(`/ai/providers/${encodeURIComponent(id)}/models/test`, json({ model })); }
export function addAiProviderModel(id: string, model: string): Promise<AiProvider> { return request(`/ai/providers/${encodeURIComponent(id)}/models`, json({ model })); }
export function setDefaultAiProviderModel(id: string, model: string): Promise<AiProvider> { return request(`/ai/providers/${encodeURIComponent(id)}/models/default`, { ...json({ model }), method: "PUT" }); }
export function deleteAiProviderModel(id: string, model: string): Promise<AiProvider> { return request(`/ai/providers/${encodeURIComponent(id)}/models?model=${encodeURIComponent(model)}`, { method: "DELETE" }); }
export function sendAiChat(payload: { provider_id: string; model: string; message: string; job_ids: string[] }, signal?: AbortSignal): Promise<AiChatResponse> { return request("/ai/chat", { ...json(payload), signal }); }
export async function fetchPromptTemplates(signal?: AbortSignal): Promise<PromptTemplate[]> { return (await request<{ items: PromptTemplate[] }>("/ai/templates", { signal })).items; }
export async function fetchAiCalls(signal?: AbortSignal): Promise<AiCallRecord[]> { return (await request<{ items: AiCallRecord[] }>("/ai/calls", { signal })).items; }
