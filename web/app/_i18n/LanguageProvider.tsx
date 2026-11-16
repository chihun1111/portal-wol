'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { readPreference, writePreference } from '../_lib/storage';

import en from './translations/en.json';
import ko from './translations/ko.json';

export type Language = 'en' | 'ko';

export type TranslateParams = Record<string, string | number>;

export type TranslateFn = (key: string, params?: TranslateParams) => string;

type LanguageContextValue = {
  language: Language;
  setLanguage: (language: Language) => void;
  toggleLanguage: () => void;
  t: TranslateFn;
};

type TranslationRecord = Record<string, unknown>;

type TranslationMap = Record<Language, TranslationRecord>;

const TRANSLATIONS: TranslationMap = {
  en: en as TranslationRecord,
  ko: ko as TranslationRecord
};

const STORAGE_KEY = 'portal-language';

const LanguageContext = createContext<LanguageContextValue | undefined>(undefined);

function interpolate(template: string, params?: TranslateParams): string {
  if (!params) {
    return template;
  }
  return template.replace(/\{([^}]+)\}/g, (match, token) => {
    const key = token.trim();
    if (!key) {
      return match;
    }
    const value = params[key];
    return value === undefined ? match : String(value);
  });
}

function resolveKey(map: TranslationRecord, key: string): unknown {
  return key.split('.').reduce<unknown>((acc, segment) => {
    if (acc && typeof acc === 'object' && segment in (acc as Record<string, unknown>)) {
      return (acc as Record<string, unknown>)[segment];
    }
    return undefined;
  }, map);
}

function createTranslator(language: Language): TranslateFn {
  return (key, params) => {
    const primary = resolveKey(TRANSLATIONS[language], key);
    const fallback = language === 'en' ? undefined : resolveKey(TRANSLATIONS.en, key);
    const value = primary ?? fallback;
    if (typeof value === 'string') {
      return interpolate(value, params);
    }
    if (typeof value === 'number') {
      return String(value);
    }
    return key;
  };
}

function getInitialLanguage(): Language {
  if (typeof window !== 'undefined') {
    const stored = readPreference(STORAGE_KEY);
    if (stored === 'en' || stored === 'ko') {
      return stored;
    }
    const browser = window.navigator.language || window.navigator.languages?.[0];
    if (browser?.toLowerCase().startsWith('en')) {
      return 'en';
    }
    if (browser?.toLowerCase().startsWith('ko')) {
      return 'ko';
    }
  }
  return 'ko';
}

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  // Match the statically exported Korean HTML before applying browser preferences.
  const [language, setLanguageState] = useState<Language>('ko');
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    const initial = getInitialLanguage();
    setLanguageState(initial);
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) {
      return;
    }
    if (typeof document !== 'undefined') {
      document.documentElement.lang = language;
    }
    if (typeof window !== 'undefined') {
      writePreference(STORAGE_KEY, language);
    }
  }, [hydrated, language]);

  const setLanguage = useCallback((next: Language) => {
    setLanguageState(next);
  }, []);

  const toggleLanguage = useCallback(() => {
    setLanguageState((prev) => (prev === 'ko' ? 'en' : 'ko'));
  }, []);

  const translator = useMemo(() => createTranslator(language), [language]);

  const value = useMemo<LanguageContextValue>(
    () => ({
      language,
      setLanguage,
      toggleLanguage,
      t: translator
    }),
    [language, setLanguage, toggleLanguage, translator]
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageContextValue {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error('useLanguage must be used within a LanguageProvider');
  }
  return context;
}
