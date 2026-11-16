import type { BootJob } from './types';

export function shouldApplyBootJobUpdate(current: BootJob | null, next: BootJob): boolean {
  // An old poll must never reopen a dismissed job or undo a terminal/cancel result.
  if (!current || current.id !== next.id || current.terminal) return false;
  return new Date(next.updated_at).getTime() >= new Date(current.updated_at).getTime();
}
