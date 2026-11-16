'use client';

import { useCallback, useEffect, useState } from 'react';
import { readPreference, writePreference } from '../_lib/storage';

type ThemeMode = 'light' | 'dark';

const STORAGE_KEY = 'wolweb_theme';

export function useTheme() {
  const [theme, setThemeState] = useState<ThemeMode>('dark');
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    const stored = readPreference(STORAGE_KEY);
    const resolved = stored === 'light' ? 'light' : 'dark';
    setThemeState(resolved);
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    document.documentElement.setAttribute('data-theme', theme);
    writePreference(STORAGE_KEY, theme);
  }, [ready, theme]);

  const applyTheme = useCallback((value: ThemeMode | ((prev: ThemeMode) => ThemeMode)) => {
    setThemeState(value);
  }, []);

  const toggleTheme = useCallback(() => {
    applyTheme((prev) => (prev === 'light' ? 'dark' : 'light'));
  }, [applyTheme]);

  return {
    theme,
    ready,
    setTheme: applyTheme,
    toggleTheme
  };
}
