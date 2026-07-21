export type GitRepositorySummary = {
  id: string;
  name: string;
  relative_path: string;
  branch: string;
  head: string | null;
  dirty: boolean;
  changed_files: number;
  last_commit_at: string | null;
};

export type GitChangedFile = { status: string; path: string };

export type GitCommitSummary = {
  hash: string;
  short_hash: string;
  subject: string;
  author_name: string;
  authored_at: string;
};

export type GitRepositoryList = {
  enabled: boolean;
  items: GitRepositorySummary[];
};

export type GitRepositoryDetail = {
  repository: GitRepositorySummary;
  changes: GitChangedFile[];
  commits: GitCommitSummary[];
  readme_name: string | null;
  readme_content: string | null;
  readme_truncated: boolean;
};

export type GitCommitDetail = GitCommitSummary & {
  body: string;
  files: GitChangedFile[];
};
