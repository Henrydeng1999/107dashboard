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

export interface JobSubmitRequest {
  name: string;
  command: string;
  partition: "Students";
  account: "stu";
  qos: "qos_stu_default";
  resources: {
    cpus: number;
    memory_mb: number;
    gpus: number;
    time_limit_minutes: number;
  };
}

export type JobLogStream = "stdout" | "stderr";

export interface JobLogResponse {
  job_id: string;
  stream: JobLogStream;
  content: string;
  offset: number;
  next_offset: number;
  eof: boolean;
  available: boolean;
}

export interface JobUsageResponse {
  job_id: string;
  requested: JobResources;
  allocated: JobResources;
  elapsed_seconds: number | null;
  time_limit_seconds: number | null;
  max_rss_kb: number | null;
  total_cpu_seconds: number | null;
  gpu_utilization_percent: number | null;
  gpu_memory_mb: number | null;
}

export interface UserJobSummary {
  total_jobs: number;
  active_jobs: number;
  successful_jobs: number;
  unsuccessful_jobs: number;
  state_counts: Record<JobState, number>;
  resources: {
    cpus: number;
    memory_mb: number;
    gpus: number;
    time_limit_minutes: number;
    cpus_jobs: number;
    memory_jobs: number;
    gpus_jobs: number;
    time_limit_jobs: number;
  };
  resource_basis: "requested_or_allocated_snapshot";
  updated_at: string;
}

export interface ApiErrorResponse {
  error?: {
    code?: string;
    message?: string;
    request_id?: string;
  };
}

export interface RuntimeCapabilities {
  list_jobs: boolean;
  job_details: boolean;
  usage: boolean;
  submit: boolean;
  cancel: boolean;
  clone: boolean;
  logs: boolean;
}

export interface RuntimeInfo {
  data_source: "fixture" | "native";
  read_only: boolean;
  capabilities: RuntimeCapabilities;
}
