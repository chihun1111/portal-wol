export type PowerAction = 'wake' | 'shutdown' | 'reboot';

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
};

export type TargetsResponse = {
  targets?: Target[];
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
