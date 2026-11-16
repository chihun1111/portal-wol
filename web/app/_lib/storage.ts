export function readPreference(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    // Storage may be blocked by browser policy or unavailable during rendering.
    return null;
  }
}

export function writePreference(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Keep the current session usable even when preferences cannot be persisted.
  }
}
