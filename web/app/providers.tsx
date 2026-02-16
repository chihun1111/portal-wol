'use client';

import type { PropsWithChildren } from 'react';

import { LanguageProvider } from './_i18n/LanguageProvider';

export function AppProviders({ children }: PropsWithChildren<{}>) {
  return (
    <LanguageProvider>{children}</LanguageProvider>
  );
}
