import type { Normalization } from '../../api/interview';
import { normalizationCopy as t } from '../../i18n/normalization';

export default function NormalizationPanel({ result }: { result?: Normalization | null }) {
  if (!result) return null;
  return (
    <div className="normalization-panel" aria-label={t.title}>
      <strong>{t.title}</strong>
      <p>{t.unverified}</p>
      {result.status === 'normalized' ? (
        result.facts.map((fact) => (
          <div key={fact.normalized_concept}>
            <p>
              <strong>{fact.normalized_display}</strong>
            </p>
            <p>
              {t.polarity}: {fact.polarity === 'absent' ? t.absent : t.present}
            </p>
            <p>
              {t.certainty}: {fact.certainty} ·{' '}
              {fact.verification_status === 'needs_verification'
                ? t.needsVerification
                : t.machineNormalized}
            </p>
            {fact.confidence !== null && (
              <p>
                {t.confidence}: {fact.confidence}
              </p>
            )}
          </div>
        ))
      ) : (
        <p>{result.status === 'unknown' ? t.unknown : t.unavailable}</p>
      )}
      <details>
        <summary>{t.provenance}</summary>
        <p>
          {t.provider}: {result.provider ?? t.notProcessed} {result.provider_version}
        </p>
        {result.model && (
          <p>
            {t.model}: {result.model}
          </p>
        )}
        {result.prompt_version && (
          <p>
            {t.prompt}: {result.prompt_version}
          </p>
        )}
        <p>
          {t.source}: {result.source_answer_id}
        </p>
        <p>
          {t.language}: {result.original_language.toUpperCase()}
        </p>
        {result.reason && (
          <p>
            {t.reason}: {result.reason.replaceAll('_', ' ')}
          </p>
        )}
      </details>
    </div>
  );
}
