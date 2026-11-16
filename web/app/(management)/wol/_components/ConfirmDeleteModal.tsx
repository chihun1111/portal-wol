'use client';

import type { Target } from '../_lib/types';
import { useLanguage } from '../../../_i18n/LanguageProvider';

type ConfirmDeleteModalProps = {
  target: Target | null;
  deleting: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmDeleteModal({ target, deleting, onConfirm, onCancel }: ConfirmDeleteModalProps) {
  const { t } = useLanguage();

  if (!target) {
    return null;
  }

  return (
    <div
      className="dialog-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-modal-title"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onCancel();
        }
      }}
    >
      <div className="dialog-shell">
        <h2 id="confirm-modal-title">{t('wol.confirmDelete.title')}</h2>
        <p>{t('wol.confirmDelete.message', { name: target.name })}</p>
        <div className="modal-actions">
          <button type="button" className="btn danger" onClick={onConfirm} disabled={deleting} data-loading={deleting ? 'true' : undefined}>
            {t('wol.confirmDelete.delete')}
          </button>
          <button type="button" className="btn ghost" onClick={onCancel} disabled={deleting}>
            {t('wol.confirmDelete.cancel')}
          </button>
        </div>
      </div>
    </div>
  );
}
