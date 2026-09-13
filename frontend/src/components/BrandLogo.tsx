import logo from '../assets/medikiosk-logo.png';
import headerWordmark from '../assets/medikiosk-header-wordmark.png';

type BrandLogoProps = {
  compact?: boolean;
  className?: string;
};

export function BrandLogo({ compact = false, className = '' }: BrandLogoProps) {
  return (
    <span
      className={`brand-lockup ${compact ? 'brand-lockup--compact' : ''} ${className}`.trim()}
      aria-label="MediKiosk — AI-Powered Pre-Consultation Clinical Screening"
    >
      <img className="brand-logo" src={logo} alt="" aria-hidden="true" />
      <img className="brand-wordmark" src={headerWordmark} alt="" aria-hidden="true" />
    </span>
  );
}
