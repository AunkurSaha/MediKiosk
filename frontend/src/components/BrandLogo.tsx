import logo from '../assets/medikiosk-logo.png';

type BrandLogoProps = {
  compact?: boolean;
  className?: string;
};

export function BrandLogo({ compact = false, className = '' }: BrandLogoProps) {
  return (
    <img
      className={`brand-logo ${compact ? 'brand-logo--compact' : ''} ${className}`.trim()}
      src={logo}
      alt="MediKiosk — AI-Powered Pre-Consultation Clinical Screening"
    />
  );
}
