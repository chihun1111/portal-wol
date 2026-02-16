'use client';

import Link from 'next/link';
import type { ChangeEventHandler } from 'react';

import { useLanguage } from '../../../_i18n/LanguageProvider';

type WolHeaderProps = {
  filter: string;
  onFilterChange: ChangeEventHandler<HTMLInputElement>;
  onRefreshStatus: () => void;
  onAddTarget: () => void;
};

export function WolHeader({ filter, onFilterChange, onRefreshStatus, onAddTarget }: WolHeaderProps) {
  const { t } = useLanguage();
  const title = t('wol.header.title');
  const subtitle = t('wol.header.subtitle');
  const searchPlaceholder = t('wol.header.searchPlaceholder');
  const refreshLabel = t('wol.header.refresh');
  const addTargetLabel = t('wol.header.addTarget');
  const settingsLabel = t('settings.linkLabel');

  return (
    <header className="page-header">
      <div className="title-block">
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      <div className="header-actions">
        <input
          id="target-filter"
          type="search"
          placeholder={searchPlaceholder}
          value={filter}
          onChange={onFilterChange}
          autoComplete="off"
        />
        <button type="button" className="btn ghost" id="status-refresh" onClick={onRefreshStatus}>
          {refreshLabel}
        </button>
        <Link className="btn ghost settings-link" href="/settings?returnTo=/wol">
          {settingsLabel}
        </Link>
        <button type="button" className="btn primary" id="add-target" onClick={onAddTarget}>
          {addTargetLabel}
        </button>
      </div>
    </header>
  );
}

