/** A monochrome KF ligature. Paths stay identical in the shell, favicon and share card. */
export function BrandSeal({ size = 28 }: { size?: number }) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} fill="none" aria-hidden="true">
      <rect x="1" y="1" width="30" height="30" rx="3" fill="#171717" />
      <path d="M8 7v18m9-18-9 9 9 9M20 25V8h6m-6 8h5" stroke="#ffffff" strokeWidth="1.8" strokeLinecap="square" strokeLinejoin="miter" />
    </svg>
  );
}
