// Used only when the domain-config fetch fails and no `validation.max_file_size_mb`
// is available to size against. backend/config/schema.py owns the real default.
export const FALLBACK_MAX_FILE_SIZE_MB = 512
