import type { DirectPowerAction } from './types';

export const ACTION_ENDPOINTS: Record<DirectPowerAction, string> = {
  wake: 'api/wake',
  shutdown: 'api/shutdown',
  reboot: 'api/reboot'
};
