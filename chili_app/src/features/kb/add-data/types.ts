/**
 * Upload progress is one piece of state shared by whichever flow is active
 * (documents or records never upload at the same time): `AddDataSection` owns
 * it and renders the single `UploadProgress` instance, while each flow reports
 * into it through these callbacks rather than holding its own copy.
 */
export type UploadCallbacks = {
  /** Marks an upload as started and remembers how to retry it verbatim. */
  beginUpload: (retry: () => void) => void
  reportUploadProgress: (percent: number) => void
  completeUpload: () => void
  failUpload: (message: string) => void
}
