import type { PowerAction } from './types';

export const ACTION_ENDPOINTS: Record<PowerAction, string> = {
  wake: 'api/wake',
  shutdown: 'api/shutdown',
  reboot: 'api/reboot'
};
