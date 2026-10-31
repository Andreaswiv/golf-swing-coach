// The app's logo. Every other icon comes from lucide-react (the shadcn/ui icon set).

export const BrandMark = ({ className = "h-7 w-7" }: { className?: string }) => (
  <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
    <rect width="32" height="32" rx="9" fill="var(--color-ink)" />
    <circle cx="16" cy="12.5" r="6" fill="white" />
    <circle cx="14" cy="11" r="0.9" fill="var(--color-brand-soft)" />
    <circle cx="17.5" cy="10.5" r="0.9" fill="var(--color-brand-soft)" />
    <circle cx="16.5" cy="14" r="0.9" fill="var(--color-brand-soft)" />
    <path d="M12.5 19.5h7l-2 3v4h-3v-4z" fill="white" opacity="0.85" />
  </svg>
);
