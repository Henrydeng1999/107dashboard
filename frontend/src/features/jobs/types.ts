export type JobState =
  | "PENDING"
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED"
  | "TIMEOUT"
  | "UNKNOWN";

export interface JobResources {
  cpus: number | null;
  memory_mb: number | null;
  gpus: number | null;
  time_limit_minutes: number | null;
}

export interface Job {
  id: string;
  slurm_job_id: string;
  owner: string;
  name: string;
  state: JobState;
  partition: string | null;
  account: string | null;
  qos: string | null;
  command: string | null;
  resources: JobResources;
  node: string | null;
  exit_code: string | null;
  reason: string | null;
  submitted_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
}

export interface JobListResponse {
  items: Job[];
  page: number;
  page_size: number;
  total: number;
  updated_at: string;
}

export interface ApiErrorResponse {
  error?: {
    code?: string;
    message?: string;
    request_id?: string;
  };
}
