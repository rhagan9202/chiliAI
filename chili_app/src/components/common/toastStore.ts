import { create } from 'zustand'

export type ToastVariant = 'info' | 'success' | 'error' | 'warning'

export interface ToastMessage {
  id: string
  variant: ToastVariant
  message: string
}

interface ToastState {
  toasts: ToastMessage[]
  push: (variant: ToastVariant, message: string) => string
  dismiss: (id: string) => void
  clear: () => void
}

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  push: (variant, message) => {
    const id =
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `toast-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    set((state) => ({
      toasts: [...state.toasts, { id, variant, message }],
    }))
    return id
  },
  dismiss: (id) =>
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id),
    })),
  clear: () => set({ toasts: [] }),
}))

export function showToast(variant: ToastVariant, message: string): string {
  return useToastStore.getState().push(variant, message)
}
