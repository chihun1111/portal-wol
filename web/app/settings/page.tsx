'use client';

import type { Route } from 'next';
import Link from 'next/link';
import { FormEvent, Suspense, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

import { useBodyClass } from '../_hooks/useBodyClass';
import { useTheme } from '../_hooks/useTheme';
import { useLanguage } from '../_i18n/LanguageProvider';
import type { Language } from '../_i18n/LanguageProvider';
import { getRequestErrorMessage, request } from '../_lib/api';
import { EMPTY_TARGET_FORM, toTargetPayload, type TargetFormState } from '../_lib/targets';

type TargetStatus = 'idle' | 'saving' | 'success' | 'error';

function isSafeInternalPath(path: string | null | undefined): path is `/${string}` {
  if (!path) return false;
  if (!path.startsWith('/')) return false;
  if (path.startsWith('//')) return false;
  if (/\s/.test(path)) return false;
  return true;
}

export default function SettingsPage() {
  return (
    <Suspense fallback={<div className="settings-suspense" aria-hidden="true" />}>
      <SettingsContent />
    </Suspense>
  );
}

function SettingsContent() {
  useBodyClass('settings-body');

  const router = useRouter();
  const searchParams = useSearchParams();

  const { language, setLanguage, t } = useLanguage();
  const { theme, setTheme } = useTheme();

  const [targetForm, setTargetForm] = useState<TargetFormState>(EMPTY_TARGET_FORM);
  const [targetStatus, setTargetStatus] = useState<TargetStatus>('idle');
  const [targetMessage, setTargetMessage] = useState('');

  const rawReturnTo = searchParams.get('returnTo');
  const returnTo = isSafeInternalPath(rawReturnTo) ? rawReturnTo : null;

  const [refPath, setRefPath] = useState<`/${string}` | null>(null);
  useEffect(() => {
    if (typeof document === 'undefined' || typeof window === 'undefined' || !document.referrer) {
      return;
    }

    try {
      const refUrl = new URL(document.referrer);
      if (refUrl.origin !== window.location.origin || !isSafeInternalPath(refUrl.pathname)) {
        return;
      }
      const composed = `${refUrl.pathname}${refUrl.search}${refUrl.hash}`;
      if (isSafeInternalPath(composed)) {
        setRefPath(composed);
      } else {
        setRefPath(refUrl.pathname);
      }
    } catch {
      // Ignore invalid referrer values.
    }
  }, []);

  const exitHref = (returnTo ?? refPath ?? '/wol') as Route;

  const updateTargetForm = (patch: Partial<TargetFormState>) => {
    setTargetStatus('idle');
    setTargetMessage('');
    setTargetForm((prev) => ({ ...prev, ...patch }));
  };

  const appearanceTitle = t('settings.appearance.title');
  const appearanceDescription = t('settings.appearance.description');
  const themeOptions = useMemo(
    () => [
      { value: 'light' as const, label: t('settings.appearance.light') },
      { value: 'dark' as const, label: t('settings.appearance.dark') }
    ],
    [t]
  );

  const languageTitle = t('settings.language.title');
  const languageDescription = t('settings.language.description');
  const languageOptions = useMemo(
    () => [
      { value: 'ko' as Language, label: t('settings.language.korean') },
      { value: 'en' as Language, label: t('settings.language.english') }
    ],
    [t]
  );

  const targetTitle = t('settings.targets.title');
  const targetDescription = t('settings.targets.description');
  const targetSubmitLabel = t('settings.targets.submit');
  const targetSuccess = t('settings.targets.success');
  const targetError = t('settings.targets.error');
  const targetHint = t('settings.targets.hint');
  const exitLabel = t('settings.actions.exit');

  const handleLanguageChange = (value: Language) => {
    setLanguage(value);
  };

  const handleThemeChange = (value: 'light' | 'dark') => {
    setTheme(value);
  };

  const handleTargetSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const payload = toTargetPayload(targetForm);
    if (!payload) {
      setTargetMessage(targetError);
      setTargetStatus('error');
      return;
    }

    setTargetStatus('saving');
    setTargetMessage('');

    try {
      await request('api/targets', {
        method: 'POST',
        body: payload
      });

      setTargetStatus('success');
      setTargetMessage(targetSuccess);
      setTargetForm(EMPTY_TARGET_FORM);
    } catch (error) {
      console.error(error);
      setTargetStatus('error');
      setTargetMessage(getRequestErrorMessage(error, targetError));
    }
  };

  return (
    <main className="settings-page">
      <header className="settings-header">
        <div className="settings-header__content">
          <h1>{t('settings.title')}</h1>
          <p>{t('settings.subtitle')}</p>
        </div>
        <div className="settings-header__actions">
          <Link
            href={exitHref}
            className="btn ghost"
            onClick={(event) => {
              event.preventDefault();
              if (!returnTo && typeof window !== 'undefined' && window.history.length > 1) {
                router.back();
              } else {
                router.push(exitHref);
              }
            }}
          >
            {exitLabel}
          </Link>
        </div>
      </header>

      <section className="settings-grid">
        <article className="settings-card">
          <h2>{appearanceTitle}</h2>
          <p className="settings-card__description">{appearanceDescription}</p>
          <div className="settings-options">
            {themeOptions.map((option) => (
              <label key={option.value} className={`settings-option${theme === option.value ? ' selected' : ''}`}>
                <input
                  type="radio"
                  name="theme"
                  value={option.value}
                  checked={theme === option.value}
                  onChange={() => handleThemeChange(option.value)}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </div>
        </article>

        <article className="settings-card">
          <h2>{languageTitle}</h2>
          <p className="settings-card__description">{languageDescription}</p>
          <div className="settings-options">
            {languageOptions.map((option) => (
              <label key={option.value} className={`settings-option${language === option.value ? ' selected' : ''}`}>
                <input
                  type="radio"
                  name="language"
                  value={option.value}
                  checked={language === option.value}
                  onChange={() => handleLanguageChange(option.value)}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </div>
        </article>

        <article className="settings-card settings-card--wide">
          <h2>{targetTitle}</h2>
          <p className="settings-card__description">{targetDescription}</p>

          <form className="settings-form" onSubmit={handleTargetSubmit}>
            <div className="settings-fields">
              <label className="settings-field">
                <span className="settings-field__label">{t('wol.targetModal.fields.name')}</span>
                <input
                  value={targetForm.name}
                  onChange={(event) => updateTargetForm({ name: event.target.value })}
                  required
                  minLength={2}
                  maxLength={32}
                  pattern="[a-z0-9-]+"
                />
                <small className="settings-field__hint">{t('wol.targetModal.fields.nameHint')}</small>
              </label>

              <label className="settings-field">
                <span className="settings-field__label">{t('wol.targetModal.fields.ip')}</span>
                <input
                  value={targetForm.ip}
                  onChange={(event) => updateTargetForm({ ip: event.target.value })}
                  required
                  placeholder={t('wol.targetModal.fields.ipPlaceholder')}
                />
              </label>

              <label className="settings-field">
                <span className="settings-field__label">{t('wol.targetModal.fields.mac')}</span>
                <input
                  value={targetForm.mac}
                  onChange={(event) => updateTargetForm({ mac: event.target.value })}
                  placeholder={t('wol.targetModal.fields.macPlaceholder')}
                />
                <small className="settings-field__hint">{t('wol.targetModal.fields.macHint')}</small>
              </label>
            </div>

            <p className={`settings-message settings-message--${targetStatus}`} role="status">
              {targetMessage || targetHint}
            </p>

            <div className="settings-actions">
              <button type="submit" className="btn primary" disabled={targetStatus === 'saving'}>
                {targetStatus === 'saving' ? t('settings.targets.saving') : targetSubmitLabel}
              </button>
              <Link href="/wol" className="btn ghost">
                {t('settings.targets.manageLink')}
              </Link>
            </div>
          </form>
        </article>
      </section>
    </main>
  );
}
