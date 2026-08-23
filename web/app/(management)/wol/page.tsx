'use client';

import type { FormEvent } from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { useBodyClass } from '../../_hooks/useBodyClass';
import { useTheme } from '../../_hooks/useTheme';
import { useLanguage, type TranslateFn } from '../../_i18n/LanguageProvider';
import { getRequestErrorCode, getRequestErrorMessage, request } from '../../_lib/api';
import { EMPTY_TARGET_FORM, toTargetPayload, type TargetFormState } from '../../_lib/targets';
import { ConfirmDeleteModal } from './_components/ConfirmDeleteModal';
import { BootJobModal } from './_components/BootJobModal';
import { ConfirmPowerModal, type PendingPowerAction } from './_components/ConfirmPowerModal';
import { LogsCard } from './_components/LogsCard';
import { WolHeader } from './_components/WolHeader';
import { TargetModal } from './_components/TargetModal';
import { TargetsCard } from './_components/TargetsCard';
import { ToastContainer } from './_components/ToastContainer';
import { useToastQueue } from './_hooks/useToastQueue';
import { ACTION_ENDPOINTS } from './_lib/constants';
import type {
  ApiLogRecord,
  BootJob,
  BootJobResponse,
  BootJobsResponse,
  DirectPowerAction,
  LogEntry,
  LogsResponse,
  PowerAction,
  Target,
  TargetsResponse
} from './_lib/types';

type RequestOptions = { silent?: boolean };

type StatusOptions = { log?: boolean };

const ACTION_LOG_LIMIT = 120;
const POWER_ACTIONS: readonly PowerAction[] = ['wake', 'shutdown', 'reboot', 'boot_ubuntu'];
const TERMINAL_BOOT_STAGES = new Set(['succeeded', 'failed', 'timed_out', 'cancelled']);

function isPowerAction(value: unknown): value is PowerAction {
  return typeof value === 'string' && POWER_ACTIONS.includes(value as PowerAction);
}

function normalizeTimestamp(value: unknown): string {
  if (typeof value !== 'string' || !value.trim()) {
    return new Date().toISOString();
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return new Date().toISOString();
  }
  return value;
}

function toDetailText(value: unknown, limit = 160): string | null {
  if (typeof value !== 'string') {
    return null;
  }
  const normalized = value.trim().replace(/\s+/g, ' ');
  if (!normalized) {
    return null;
  }
  if (normalized.length <= limit) {
    return normalized;
  }
  return `${normalized.slice(0, Math.max(limit - 3, 0))}...`;
}

function mapApiLogsToEntries(records: ApiLogRecord[] | undefined, t: TranslateFn): LogEntry[] {
  if (!Array.isArray(records)) {
    return [];
  }

  const mapped: LogEntry[] = [];
  records.forEach((record, index) => {
    const rawAction = record.evt === 'boot-ubuntu' ? 'boot_ubuntu' : record.evt;
    if (!isPowerAction(rawAction)) {
      return;
    }
    const action = rawAction;
    if (action === 'boot_ubuntu' && (!record.stage || !TERMINAL_BOOT_STAGES.has(record.stage))) {
      return;
    }
    const target = typeof record.target === 'string' && record.target.trim() ? record.target.trim() : '-';
    const actionLabel = t(`wol.actions.labels.${action}`);
    const failed =
      (typeof record.rc === 'number' && record.rc !== 0) ||
      Boolean(record.error) ||
      (action === 'boot_ubuntu' && record.stage !== 'succeeded');
    const status: LogEntry['status'] = failed ? 'error' : 'success';
    const baseMessage = action === 'boot_ubuntu'
      ? status === 'success'
        ? t('wol.boot.completed', { target })
        : record.stage === 'cancelled'
          ? t('wol.boot.cancelled')
          : t(`wol.boot.errors.${record.error_code ?? 'internal_error'}`)
      : status === 'success'
        ? t('wol.actions.success', { action: actionLabel, target })
        : t('wol.actions.failure', { action: actionLabel });
    const detail = action === 'boot_ubuntu'
      ? null
      : toDetailText(record.stderr) ?? toDetailText(record.message) ?? toDetailText(record.error);
    const message = status === 'error' && detail ? `${baseMessage} (${detail})` : baseMessage;
    mapped.push({
      id: `api-${record.ts ?? 'na'}-${action}-${target}-${index}`,
      timestamp: normalizeTimestamp(record.ts),
      action,
      target,
      status,
      message
    });
  });
  return mapped.slice(0, ACTION_LOG_LIMIT);
}

export default function WolPage() {
  useBodyClass('wol-body');

  useTheme();
  const { t } = useLanguage();
  const { toasts, showToast } = useToastQueue();

  const [targets, setTargets] = useState<Target[]>([]);
  const targetsRef = useRef<Target[]>([]);
  const [filter, setFilter] = useState('');
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [targetModalOpen, setTargetModalOpen] = useState(false);
  const [targetModalMode, setTargetModalMode] = useState<'create' | 'edit'>('create');
  const [targetForm, setTargetForm] = useState<TargetFormState>(EMPTY_TARGET_FORM);
  const [targetError, setTargetError] = useState('');
  const [editingTarget, setEditingTarget] = useState<Target | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<Target | null>(null);
  const [pendingPowerAction, setPendingPowerAction] = useState<PendingPowerAction | null>(null);
  const [bootJob, setBootJob] = useState<BootJob | null>(null);
  const [bootCancelling, setBootCancelling] = useState(false);
  const [actionLoadingKey, setActionLoadingKey] = useState<string | null>(null);
  const loadingTargetsRef = useRef(false);
  const statusRefreshingRef = useRef(false);
  const handledBootJobsRef = useRef<Set<string>>(new Set());

  const appendLog = useCallback((entry: LogEntry) => {
    setLogs((prev) => [entry, ...prev].slice(0, ACTION_LOG_LIMIT));
  }, []);

  const updateLog = useCallback((id: string, patch: Partial<LogEntry>) => {
    setLogs((prev) => prev.map((log) => (log.id === id ? { ...log, ...patch } : log)));
  }, []);

  const clearLogs = useCallback(() => {
    setLogs([]);
  }, []);

  const loadLogs = useCallback(async () => {
    try {
      const data = await request<LogsResponse>(`api/logs?limit=${ACTION_LOG_LIMIT}`);
      const persistedLogs = mapApiLogsToEntries(data?.logs, t);
      setLogs((prev) => {
        const pendingLogs = prev.filter((entry) => entry.status === 'pending');
        if (!pendingLogs.length) {
          return persistedLogs;
        }
        return [...pendingLogs, ...persistedLogs].slice(0, ACTION_LOG_LIMIT);
      });
    } catch (error) {
      console.warn('logs load error', error);
    }
  }, [t]);

  useEffect(() => {
    targetsRef.current = targets;
  }, [targets]);

  const loadTargets = useCallback(async ({ silent = false }: RequestOptions = {}) => {
    if (loadingTargetsRef.current) return;
    loadingTargetsRef.current = true;
    try {
      const data = await request<TargetsResponse>('api/targets');
      const list = Array.isArray(data?.targets) ? data.targets : [];
      setTargets(list);
      if (!silent) {
        showToast(t('wol.toasts.targetsLoaded'), 'success');
      }
    } catch (error) {
      console.error(error);
      showToast(t('wol.toasts.targetsLoadFailed'), 'error');
    } finally {
      loadingTargetsRef.current = false;
    }
  }, [showToast, t]);

  const refreshStatuses = useCallback(async ({ log = false }: StatusOptions = {}) => {
    if (statusRefreshingRef.current || !targetsRef.current.length) {
      return;
    }
    statusRefreshingRef.current = true;
    const silentParam = log ? 'false' : 'true';
    try {
      for (const target of targetsRef.current) {
        try {
          await request(`api/status?target=${encodeURIComponent(target.name)}&silent=${silentParam}`);
        } catch (error) {
          console.warn('status error', target.name, error);
        }
      }
      await loadTargets({ silent: true });
      if (log) {
        showToast(t('wol.toasts.statusesRefreshed'), 'success');
      }
    } finally {
      statusRefreshingRef.current = false;
    }
  }, [loadTargets, showToast, t]);

  useEffect(() => {
    loadTargets({ silent: true });
  }, [loadTargets]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  const applyBootJobUpdate = useCallback(
    (job: BootJob) => {
      setBootJob(job);
      if (!job.terminal || handledBootJobsRef.current.has(job.id)) {
        return;
      }
      handledBootJobsRef.current.add(job.id);
      if (job.state === 'succeeded') {
        showToast(t('wol.boot.completed', { target: job.target }), 'success');
      } else if (job.state === 'cancelled') {
        showToast(t('wol.boot.cancelled'), 'info');
      } else {
        showToast(t(`wol.boot.errors.${job.error_code ?? 'internal_error'}`), 'error');
      }
      loadLogs();
    },
    [loadLogs, showToast, t]
  );

  const restoreActiveBootJob = useCallback(async () => {
    try {
      const data = await request<BootJobsResponse>('api/jobs?target=mainpc&limit=20');
      const active = data.jobs?.find((job) => !job.terminal);
      if (active) {
        setBootJob(active);
      }
    } catch (error) {
      console.warn('boot job restore error', error);
    }
  }, []);

  useEffect(() => {
    restoreActiveBootJob();
  }, [restoreActiveBootJob]);

  useEffect(() => {
    if (!bootJob || bootJob.terminal) {
      return;
    }
    const poll = async () => {
      try {
        const data = await request<BootJobResponse>(`api/jobs/${encodeURIComponent(bootJob.id)}`);
        applyBootJobUpdate(data.job);
      } catch (error) {
        console.warn('boot job poll error', error);
      }
    };
    const interval = window.setInterval(poll, 2000);
    return () => window.clearInterval(interval);
  }, [applyBootJobUpdate, bootJob]);

  useEffect(() => {
    if (!targets.length) {
      return;
    }
    const interval = window.setInterval(() => {
      refreshStatuses({ log: false });
    }, 15_000);
    return () => window.clearInterval(interval);
  }, [targets.length, refreshStatuses]);

  const filteredTargets = useMemo(() => {
    const term = filter.trim().toLowerCase();
    if (!term) return targets;
    return targets.filter((target) => {
      const nameMatch = target.name.toLowerCase().includes(term);
      const ipMatch = (target.ip ?? '').toLowerCase().includes(term);
      return nameMatch || ipMatch;
    });
  }, [filter, targets]);

  const closeTargetModal = useCallback(() => {
    setTargetModalOpen(false);
    setEditingTarget(null);
  }, []);

  const openCreateModal = useCallback(() => {
    setTargetModalMode('create');
    setTargetForm(EMPTY_TARGET_FORM);
    setTargetError('');
    setEditingTarget(null);
    setTargetModalOpen(true);
  }, []);

  const openEditModal = useCallback((target: Target) => {
    setTargetModalMode('edit');
    setEditingTarget(target);
    setTargetForm({ name: target.name ?? '', ip: target.ip ?? '', mac: target.mac ?? '' });
    setTargetError('');
    setTargetModalOpen(true);
  }, []);

  const openConfirmModal = useCallback((target: Target) => {
    setConfirmTarget(target);
  }, []);

  useEffect(() => {
    setTargetError('');
  }, [targetModalOpen]);

  const handleTargetSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const payload = toTargetPayload(targetForm, {
        includeEmptyMac: targetModalMode === 'edit'
      });

      if (!payload) {
        const message = t('wol.toasts.missingFields');
        setTargetError(message);
        return;
      }

      try {
        if (targetModalMode === 'edit' && editingTarget) {
          await request(`api/targets/${encodeURIComponent(editingTarget.name)}`, {
            method: 'PATCH',
            body: payload
          });
          showToast(t('wol.toasts.targetUpdated'), 'success');
        } else {
          await request('api/targets', {
            method: 'POST',
            body: payload
          });
          showToast(t('wol.toasts.targetAdded'), 'success');
        }
        closeTargetModal();
        setEditingTarget(null);
        setTargetError('');
        setTargetForm(EMPTY_TARGET_FORM);
        await loadTargets({ silent: true });
      } catch (error) {
        console.error(error);
        setTargetError(getRequestErrorMessage(error, t('wol.toasts.saveFailed')));
      }
    },
    [closeTargetModal, editingTarget, loadTargets, showToast, t, targetForm, targetModalMode]
  );

  const handleDelete = useCallback(async () => {
    if (!confirmTarget) {
      return;
    }
    try {
      await request(`api/targets/${encodeURIComponent(confirmTarget.name)}`, { method: 'DELETE' });
      showToast(t('wol.toasts.targetDeleted'), 'success');
      await loadTargets({ silent: true });
    } catch (error) {
      console.error(error);
      showToast(t('wol.toasts.deleteFailed'), 'error');
    } finally {
      setConfirmTarget(null);
    }
  }, [confirmTarget, loadTargets, showToast, t]);

  const handleAction = useCallback(
    async (target: Target, action: DirectPowerAction) => {
      if (action === 'wake' && !target.has_mac) {
        showToast(t('wol.toasts.macRequired'), 'warning');
        return;
      }
      const path = ACTION_ENDPOINTS[action];
      if (!path) {
        return;
      }
      const key = `${action}:${target.name}`;
      const logId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const actionLabel = t(`wol.actions.labels.${action}`);
      setActionLoadingKey(key);
      appendLog({
        id: logId,
        timestamp: new Date().toISOString(),
        action,
        target: target.name,
        status: 'pending',
        message: t('wol.actions.progress', { action: actionLabel, target: target.name })
      });
      try {
        await request(path, {
          method: 'POST',
          body: { target: target.name }
        });
        const successMessage = t('wol.actions.success', { action: actionLabel, target: target.name });
        updateLog(logId, {
          status: 'success',
          message: successMessage
        });
        showToast(successMessage, 'success');
        await loadTargets({ silent: true });
      } catch (error) {
        console.error(error);
        const failureMessage = t('wol.actions.failure', { action: actionLabel });
        const message = getRequestErrorMessage(error, failureMessage);
        updateLog(logId, {
          status: 'error',
          message
        });
        showToast(message, 'error');
      } finally {
        setActionLoadingKey(null);
      }
    },
    [appendLog, loadTargets, showToast, t, updateLog]
  );

  const requestDirectAction = useCallback(
    (target: Target, action: DirectPowerAction) => {
      if (action === 'wake') {
        handleAction(target, action);
        return;
      }
      setPendingPowerAction({ target, action });
    },
    [handleAction]
  );

  const startBootUbuntu = useCallback(
    async (target: Target) => {
      const key = `boot_ubuntu:${target.name}`;
      setActionLoadingKey(key);
      try {
        const data = await request<BootJobResponse>('api/boot/ubuntu', {
          method: 'POST',
          body: { target: target.name }
        });
        setBootJob(data.job);
        showToast(t('wol.boot.started', { target: target.name }), 'info');
      } catch (error) {
        console.error(error);
        await restoreActiveBootJob();
        const errorCode = getRequestErrorCode(error);
        showToast(errorCode ? t(`wol.boot.errors.${errorCode}`) : t('wol.boot.startFailed'), 'error');
      } finally {
        setActionLoadingKey(null);
      }
    },
    [restoreActiveBootJob, showToast, t]
  );

  const confirmPowerAction = useCallback(async () => {
    const pending = pendingPowerAction;
    setPendingPowerAction(null);
    if (!pending) return;
    if (pending.action === 'boot_ubuntu') {
      await startBootUbuntu(pending.target);
      return;
    }
    await handleAction(pending.target, pending.action);
  }, [handleAction, pendingPowerAction, startBootUbuntu]);

  const cancelBootJob = useCallback(async () => {
    if (!bootJob || !bootJob.can_cancel || bootJob.terminal) return;
    setBootCancelling(true);
    try {
      const data = await request<BootJobResponse>(`api/jobs/${encodeURIComponent(bootJob.id)}/cancel`, {
        method: 'POST'
      });
      applyBootJobUpdate(data.job);
    } catch (error) {
      const errorCode = getRequestErrorCode(error);
      showToast(errorCode ? t(`wol.boot.errors.${errorCode}`) : t('wol.boot.cancelFailed'), 'error');
    } finally {
      setBootCancelling(false);
    }
  }, [applyBootJobUpdate, bootJob, showToast, t]);

  return (
    <div className="page-shell">
      <WolHeader
        filter={filter}
        onFilterChange={(event) => setFilter(event.target.value)}
        onRefreshStatus={() => refreshStatuses({ log: true })}
        onAddTarget={openCreateModal}
      />

      <main className="layout">
        <TargetsCard
          targets={targets}
          filteredTargets={filteredTargets}
          actionLoadingKey={actionLoadingKey}
          onAction={requestDirectAction}
          onBootUbuntu={(target) => setPendingPowerAction({ target, action: 'boot_ubuntu' })}
          onEdit={openEditModal}
          onDelete={openConfirmModal}
        />
        <LogsCard logs={logs} onClear={clearLogs} />
      </main>

      <ToastContainer toasts={toasts} />

      <TargetModal
        open={targetModalOpen}
        mode={targetModalMode}
        form={targetForm}
        error={targetError}
        onChange={setTargetForm}
        onClose={closeTargetModal}
        onSubmit={handleTargetSubmit}
      />

      <ConfirmDeleteModal target={confirmTarget} onConfirm={handleDelete} onCancel={() => setConfirmTarget(null)} />
      <ConfirmPowerModal
        pending={pendingPowerAction}
        onConfirm={confirmPowerAction}
        onCancel={() => setPendingPowerAction(null)}
      />
      <BootJobModal
        job={bootJob}
        cancelling={bootCancelling}
        onCancel={cancelBootJob}
        onClose={() => setBootJob(null)}
      />
    </div>
  );
}
