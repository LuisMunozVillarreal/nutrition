export interface PromiseSubscription<T> {
  onFulfilled: (value: T) => void
  onRejected: (error: unknown) => void
  onSettled: () => void
}

export function subscribeToPromise<T>(
  promise: Promise<T>,
  subscription: PromiseSubscription<T>,
): () => void {
  let cancelled = false

  void promise.then(
    (value) => {
      if (cancelled) return
      subscription.onFulfilled(value)
      subscription.onSettled()
    },
    (error: unknown) => {
      if (cancelled) return
      subscription.onRejected(error)
      subscription.onSettled()
    },
  )

  return () => {
    cancelled = true
  }
}
