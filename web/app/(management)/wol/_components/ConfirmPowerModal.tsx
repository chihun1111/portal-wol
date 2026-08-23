'use client';

import { useLanguage } from '../../../_i18n/LanguageProvider';
import type { ConfirmablePowerAction, Target } from '../_lib/types';

export type PendingPowerAction = {
  target: Target;
  action: ConfirmablePowerAction;
};

type ConfirmPowerModalProps = {
  pending: PendingPowerAction | null;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmPowerModal({ pending, onConfirm, onCancel }: ConfirmPowerModalProps) {
  const { t } = useLanguage();

  if (!pending) {
    return null;
  }

  const { action, target } = pending;
  const confirmClass = action === 'shutdown' ? 'btn danger' : action === 'boot_ubuntu' ? 'btn primary' : 'btn secondary';

  return (
    <div
      className="dialog-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-power-title"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onCancel();
        }
      }}
    >
      <div className="dialog-shell">
        <h2 id="confirm-power-title">{t(`wol.confirmPower.${action}.title`)}</h2>
        <p>{t(`wol.confirmPower.${action}.message`, { name: target.name })}</p>
        {action === 'boot_ubuntu' ? <p className="dialog-note">{t('wol.confirmPower.boot_ubuntu.note')}</p> : null}
        <div className="modal-actions">
          <button type="button" className={confirmClass} onClick={onConfirm}>
            {t(`wol.confirmPower.${action}.confirm`)}
          </button>
          <button type="button" className="btn ghost" onClick={onCancel}>
            {t('common.buttons.cancel')}
          </button>
        </div>
      </div>
    </div>
  );
}
