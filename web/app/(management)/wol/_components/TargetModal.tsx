'use client';

import type { FormEventHandler } from 'react';

import { useLanguage } from '../../../_i18n/LanguageProvider';
import type { TargetFormState } from '../../../_lib/targets';

type TargetModalProps = {
  open: boolean;
  mode: 'create' | 'edit';
  form: TargetFormState;
  error: string;
  onChange: (form: TargetFormState) => void;
  onClose: () => void;
  onSubmit: FormEventHandler<HTMLFormElement>;
};

export function TargetModal({ open, mode, form, error, onChange, onClose, onSubmit }: TargetModalProps) {
  const { t } = useLanguage();

  if (!open) {
    return null;
  }

  const title = mode === 'edit' ? t('wol.targetModal.title.edit') : t('wol.targetModal.title.create');

  return (
    <div
      className="dialog-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="target-modal-title"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div className="dialog-shell">
        <form id="target-form" onSubmit={onSubmit}>
          <h2 id="target-modal-title">{title}</h2>
          <label className="field">
            <span>{t('wol.targetModal.fields.name')}</span>
            <input
              name="name"
              value={form.name}
              onChange={(event) => onChange({ ...form, name: event.target.value })}
              required
              minLength={2}
              maxLength={32}
              pattern="[a-z0-9-]+"
              autoComplete="off"
            />
            <small>{t('wol.targetModal.fields.nameHint')}</small>
          </label>
          <label className="field">
            <span>{t('wol.targetModal.fields.ip')}</span>
            <input
              name="ip"
              value={form.ip}
              onChange={(event) => onChange({ ...form, ip: event.target.value })}
              required
              placeholder={t('wol.targetModal.fields.ipPlaceholder')}
              autoComplete="off"
            />
          </label>
          <details className="field advanced" open={Boolean(form.mac)}>
            <summary>{t('wol.targetModal.fields.advancedSummary')}</summary>
            <label>
              <span>{t('wol.targetModal.fields.mac')}</span>
              <input
                name="mac"
                value={form.mac}
                onChange={(event) => onChange({ ...form, mac: event.target.value })}
                placeholder={t('wol.targetModal.fields.macPlaceholder')}
                autoComplete="off"
              />
            </label>
            <small>{t('wol.targetModal.fields.macHint')}</small>
          </details>
          <p className="form-error" id="target-form-error">
            {error}
          </p>
          <div className="modal-actions">
            <button type="submit" className="btn primary" id="target-save">
              {t('wol.targetModal.actions.save')}
            </button>
            <button type="button" className="btn ghost" onClick={onClose}>
              {t('wol.targetModal.actions.cancel')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
