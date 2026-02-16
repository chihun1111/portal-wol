export type TargetFormState = {
  name: string;
  ip: string;
  mac: string;
};

export type TargetPayload = {
  name: string;
  ip: string;
  mac?: string;
};

export const EMPTY_TARGET_FORM: TargetFormState = {
  name: '',
  ip: '',
  mac: ''
};

function normalizeMac(mac: string): string {
  return mac.trim().replace(/-/g, ':').toUpperCase();
}

export function normalizeTargetForm(form: TargetFormState): TargetFormState {
  return {
    name: form.name.trim(),
    ip: form.ip.trim(),
    mac: normalizeMac(form.mac)
  };
}

export function toTargetPayload(
  form: TargetFormState,
  options: { includeEmptyMac?: boolean } = {}
): TargetPayload | null {
  const normalized = normalizeTargetForm(form);
  if (!normalized.name || !normalized.ip) {
    return null;
  }

  const payload: TargetPayload = {
    name: normalized.name,
    ip: normalized.ip
  };

  if (normalized.mac || options.includeEmptyMac) {
    payload.mac = normalized.mac;
  }

  return payload;
}
