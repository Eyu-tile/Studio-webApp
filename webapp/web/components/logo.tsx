export function Logo({ size = 26 }: { size?: number }) {
  return (
    <span className="inline-flex items-center justify-center rounded-lg bg-text text-bg" style={{ width: size, height: size }}>
      <svg viewBox="0 0 24 24" width={size * 0.58} height={size * 0.58} fill="none" aria-hidden>
        <rect x="3" y="5" width="13" height="14" rx="2.5" stroke="currentColor" strokeWidth="2" />
        <path d="M16 10.5 21 7.5v9l-5-3" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      </svg>
    </span>
  );
}
