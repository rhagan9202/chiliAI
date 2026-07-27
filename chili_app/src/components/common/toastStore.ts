import { create } from 'zustand'

export type ToastVariant = 'info' | 'success' | 'error' | 'warning'

/** An in-app destination the toast can offer, e.g. the case it just created. */
export interface ToastAction {
  label: string
  to: string
}

export interface ToastMessage {
  id: string
  variant: ToastVariant
  message: string
  action?: ToastAction
}

interface ToastState {
  toasts: ToastMessage[]
  push: (variant: ToastVariant, message: string, action?: ToastAction) => string
  dismiss: (id: string) => void
  clear: () => void
}

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  push: (variant, message, action) => {
    const id =
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `toast-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    set((state) => ({
      toasts: [...state.toasts, { id, variant, message, ...(action ? { action } : {}) }],
    }))
    return id
  },
  dismiss: (id) =>
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id),
    })),
  clear: () => set({ toasts: [] }),
}))

export function showToast(
  variant: ToastVariant,
  message: string,
  action?: ToastAction,
): string {
  return useToastStore.getState().push(variant, message, action)
}
