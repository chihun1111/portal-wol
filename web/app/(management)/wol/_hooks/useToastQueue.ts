'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import type { ToastState, ToastVariant } from '../_lib/types';

export function useToastQueue() {
  const [toasts, setToasts] = useState<ToastState[]>([]);
  const timersRef = useRef(new Set<number>());
  const mountedRef = useRef(false);

  useEffect(() => {
    mountedRef.current = true;
    const timers = timersRef.current;
    return () => {
      mountedRef.current = false;
      timers.forEach((timer) => window.clearTimeout(timer));
      timers.clear();
    };
  }, []);

  const showToast = useCallback((message: string, variant: ToastVariant = 'info') => {
    if (!mountedRef.current) return;
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev, { id, message, variant, active: false }]);

    const activateTimer = window.setTimeout(() => {
      timersRef.current.delete(activateTimer);
      setToasts((prev) => prev.map((toast) => (toast.id === id ? { ...toast, active: true } : toast)));
    }, 20);

    const removeTimer = window.setTimeout(() => {
      timersRef.current.delete(removeTimer);
      setToasts((prev) => prev.filter((toast) => toast.id !== id));
    }, 3200);
    timersRef.current.add(activateTimer);
    timersRef.current.add(removeTimer);
  }, []);

  return { toasts, showToast };
}
