'use client';

import type { DirectPowerAction, Target } from '../_lib/types';
import { formatRelative } from '../_lib/format';
import { useLanguage } from '../../../_i18n/LanguageProvider';

type TargetsCardProps = {
  targets: Target[];
  filteredTargets: Target[];
  actionLoadingKey: string | null;
  onAction: (target: Target, action: DirectPowerAction) => void;
  onBootUbuntu: (target: Target) => void;
  onEdit: (target: Target) => void;
  onDelete: (target: Target) => void;
};

export function TargetsCard({
  targets,
  filteredTargets,
  actionLoadingKey,
  onAction,
  onBootUbuntu,
  onEdit,
  onDelete
}: TargetsCardProps) {
  const { t } = useLanguage();
  const title = t('wol.targets.title');
  const subtitle = t('wol.targets.subtitle');
  const summary = t('wol.targets.summary', { total: targets.length, showing: filteredTargets.length });
  const columnLabels = {
    name: t('wol.targets.columns.name'),
    ip: t('wol.targets.columns.ip'),
    mac: t('wol.targets.columns.mac'),
    status: t('wol.targets.columns.status'),
    recent: t('wol.targets.columns.recent'),
    actions: t('wol.targets.columns.actions')
  };
  const statusLabels = {
    online: t('wol.targets.status.online'),
    offline: t('wol.targets.status.offline'),
    unknown: t('wol.targets.status.unknown')
  };
  const macNotSet = t('wol.targets.macNotSet');
  const macBadge = t('wol.targets.macMissingBadge');
  const wakeDisabledLabel = t('wol.targets.wakeDisabled');
  const wakeTitle = t('wol.targets.wakeTitle');
  const actionLabels = {
    wake: t('wol.targets.actions.wake'),
    shutdown: t('wol.targets.actions.shutdown'),
    reboot: t('wol.targets.actions.reboot'),
    bootUbuntu: t('wol.targets.actions.bootUbuntu'),
    edit: t('wol.targets.actions.edit'),
    delete: t('wol.targets.actions.delete')
  };
  const emptyState = t('wol.targets.empty');

  return (
    <section className="card targets-card">
      <div className="card-header">
        <div>
          <h2>{title}</h2>
          <p className="card-subtitle">{subtitle}</p>
        </div>
        <span className="status-indicator" id="status-indicator">
          {summary}
        </span>
      </div>
      <div className="table-wrapper">
        <table className="targets-table">
          <thead>
            <tr>
              <th>{columnLabels.name}</th>
              <th>{columnLabels.ip}</th>
              <th>{columnLabels.mac}</th>
              <th>{columnLabels.status}</th>
              <th>{columnLabels.recent}</th>
              <th className="actions-col">{columnLabels.actions}</th>
            </tr>
          </thead>
          <tbody>
            {filteredTargets.map((target) => {
              const status = target.online === true ? 'online' : target.online === false ? 'offline' : 'unknown';
              const statusLabel =
                status === 'online' ? statusLabels.online : status === 'offline' ? statusLabels.offline : statusLabels.unknown;
              const badgeClass = status === 'online' ? 'badge online' : status === 'offline' ? 'badge offline' : 'badge';
              const mac = target.mac || macNotSet;
              const macClass = target.mac ? '' : 'mac-missing';
              const recent = target.last_wake_at || target.last_status_at || target.updated_at || target.created_at;
              const wakeDisabled = !target.has_mac;
              const wakeKey = `wake:${target.name}`;
              const shutdownKey = `shutdown:${target.name}`;
              const rebootKey = `reboot:${target.name}`;
              const bootUbuntuKey = `boot_ubuntu:${target.name}`;

              return (
                <tr key={target.name}>
                  <td data-label={columnLabels.name}>
                    <div className="target-name">{target.name}</div>
                    {!target.has_mac ? <span className="badge warn">{macBadge}</span> : null}
                  </td>
                  <td data-label={columnLabels.ip}>{target.ip ?? '-'}</td>
                  <td data-label={columnLabels.mac} className={macClass}>
                    {mac}
                  </td>
                  <td data-label={columnLabels.status}>
                    <span className={badgeClass}>{statusLabel}</span>
                  </td>
                  <td data-label={columnLabels.recent}>{formatRelative(recent, t)}</td>
                  <td className="actions" data-label={columnLabels.actions}>
                    <div className="button-group">
                      <button
                        className="btn small"
                        data-action="wake"
                        data-name={target.name}
                        disabled={wakeDisabled}
                        title={wakeDisabled ? wakeDisabledLabel : wakeTitle}
                        data-loading={actionLoadingKey === wakeKey ? 'true' : undefined}
                        onClick={() => onAction(target, 'wake')}
                      >
                        {actionLabels.wake}
                      </button>
                      <button
                        className="btn small secondary"
                        data-action="shutdown"
                        data-name={target.name}
                        data-loading={actionLoadingKey === shutdownKey ? 'true' : undefined}
                        onClick={() => onAction(target, 'shutdown')}
                      >
                        {actionLabels.shutdown}
                      </button>
                      <button
                        className="btn small secondary"
                        data-action="reboot"
                        data-name={target.name}
                        data-loading={actionLoadingKey === rebootKey ? 'true' : undefined}
                        onClick={() => onAction(target, 'reboot')}
                      >
                        {actionLabels.reboot}
                      </button>
                      {target.can_boot_ubuntu ? (
                        <button
                          className="btn small primary"
                          data-action="boot_ubuntu"
                          data-name={target.name}
                          data-loading={actionLoadingKey === bootUbuntuKey ? 'true' : undefined}
                          onClick={() => onBootUbuntu(target)}
                        >
                          {actionLabels.bootUbuntu}
                        </button>
                      ) : null}
                    </div>
                    <div className="button-group secondary">
                      <button className="btn small ghost" onClick={() => onEdit(target)}>
                        {actionLabels.edit}
                      </button>
                      <button className="btn small ghost" onClick={() => onDelete(target)}>
                        {actionLabels.delete}
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {filteredTargets.length === 0 ? <div className="empty-state">{emptyState}</div> : null}
      </div>
    </section>
  );
}
