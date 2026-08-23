'use client';

import { useEffect, useState } from 'react';

import { useLanguage } from '../../../_i18n/LanguageProvider';
import type { BootJob } from '../_lib/types';

type BootJobModalProps = {
  job: BootJob | null;
  startedAt: number | null;
  cancelling: boolean;
  onCancel: () => void;
  onClose: () => void;
};

function elapsedSeconds(createdAt: string, startedAt: number | null, now: number): number {
  const created = startedAt ?? new Date(createdAt).getTime();
  if (Number.isNaN(created)) return 0;
  return Math.max(0, Math.floor((now - created) / 1000));
}

export function BootJobModal({ job, startedAt, cancelling, onCancel, onClose }: BootJobModalProps) {
  const { t } = useLanguage();
  const [now, setNow] = useState(() => Date.now());
  const jobId = job?.id;
  const jobTerminal = job?.terminal;

  useEffect(() => {
    setNow(Date.now());
    if (!jobId || jobTerminal) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [jobId, jobTerminal]);

  if (!job) {
    return null;
  }

  const errorMessage = job.error_code ? t(`wol.boot.errors.${job.error_code}`) : null;

  return (
    <div className="dialog-backdrop" role="dialog" aria-modal="true" aria-labelledby="boot-job-title">
      <div className="dialog-shell boot-job-dialog">
        <h2 id="boot-job-title">{t('wol.boot.title', { name: job.target })}</h2>
        <div className={`boot-job-status boot-job-status--${job.state}`}>
          <span className="boot-job-status__dot" aria-hidden="true" />
          <strong>{t(`wol.boot.stages.${job.stage}`)}</strong>
        </div>
        <dl className="boot-job-details">
          <div>
            <dt>{t('wol.boot.elapsed')}</dt>
            <dd>{t('wol.boot.elapsedValue', { seconds: elapsedSeconds(job.created_at, startedAt, now) })}</dd>
          </div>
          <div>
            <dt>{t('wol.boot.jobId')}</dt>
            <dd title={job.id}>{job.id.slice(0, 8)}</dd>
          </div>
        </dl>
        {errorMessage ? <p className="boot-job-error">{errorMessage}</p> : null}
        <div className="modal-actions">
          {!job.terminal && job.can_cancel ? (
            <button type="button" className="btn secondary" disabled={cancelling} onClick={onCancel}>
              {cancelling ? t('wol.boot.cancelling') : t('wol.boot.cancel')}
            </button>
          ) : null}
          {job.terminal ? (
            <button type="button" className="btn primary" onClick={onClose}>
              {t('common.buttons.close')}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
