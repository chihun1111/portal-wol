export type PowerAction = 'wake' | 'shutdown' | 'reboot' | 'boot_ubuntu';
export type DirectPowerAction = Exclude<PowerAction, 'boot_ubuntu'>;
export type ConfirmablePowerAction = Extract<PowerAction, 'shutdown' | 'reboot' | 'boot_ubuntu'>;

export type Target = {
  name: string;
  ip?: string;
  mac?: string;
  has_mac?: boolean;
  online?: boolean | null;
  last_wake_at?: string | null;
  last_status_at?: string | null;
  updated_at?: string | null;
  created_at?: string | null;
  can_boot_ubuntu?: boolean;
};

export type TargetsResponse = {
  targets?: Target[];
};

export type ApiLogRecord = {
  evt?: string;
  target?: string;
  ts?: string;
  rc?: number;
  error?: string;
  stderr?: string;
  message?: string;
  stage?: string;
  error_code?: string;
};

export type LogsResponse = {
  logs?: ApiLogRecord[];
};

export type LogStatus = 'pending' | 'success' | 'error';

export type LogEntry = {
  id: string;
  timestamp: string;
  action: PowerAction;
  target: string;
  status: LogStatus;
  message: string;
};

export type ToastVariant = 'success' | 'error' | 'info' | 'warning';

export type ToastState = {
  id: number;
  message: string;
  variant: ToastVariant;
  active: boolean;
};

export type BootJobState = 'queued' | 'running' | 'succeeded' | 'failed' | 'timed_out' | 'cancelled';

export type BootJobStage =
  | 'queued'
  | 'detecting_os'
  | 'waking'
  | 'waiting_for_windows'
  | 'windows_login_ready'
  | 'setting_bootnext'
  | 'rebooting'
  | 'waiting_for_ubuntu'
  | 'succeeded'
  | 'failed'
  | 'timed_out'
  | 'cancelled';

export type BootJob = {
  id: string;
  target: string;
  state: BootJobState;
  stage: BootJobStage;
  terminal: boolean;
  can_cancel: boolean;
  created_at: string;
  updated_at: string;
  error_code?: string | null;
};

export type BootJobResponse = { job: BootJob };
export type BootJobsResponse = { jobs?: BootJob[] };
