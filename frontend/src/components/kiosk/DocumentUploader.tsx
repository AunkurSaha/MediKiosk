import { useEffect, useRef, useState } from 'react';
import { api, ApiError } from '../../api/client';
import type { DocumentRecord, Language } from '../../api/client';
import { copy } from '../../i18n';

interface DocumentUploaderProps {
  sessionId: string;
  language: Language;
  documentConsent: boolean;
  onUploadComplete?: (doc: DocumentRecord) => void;
}

export default function DocumentUploader({
  sessionId,
  language,
  documentConsent,
  onUploadComplete,
}: DocumentUploaderProps) {
  const t = copy[language];
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [docType, setDocType] = useState<'prescription' | 'lab_report' | 'other'>('prescription');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load any previously uploaded documents for this session
  useEffect(() => {
    let active = true;
    if (!documentConsent) return;
    api
      .documents(sessionId)
      .then((res) => {
        if (active) setDocuments(res.documents);
      })
      .catch(() => {
        // Silently tolerate list failure on load
      });
    return () => {
      active = false;
    };
  }, [sessionId, documentConsent]);

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setError(null);

    // Client-side validation: size <= 10MB
    const maxBytes = 10 * 1024 * 1024;
    if (file.size > maxBytes) {
      setError('Document exceeds the 10MB size limit.');
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }

    // Client-side media type validation
    const allowed = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'];
    if (!allowed.includes(file.type)) {
      setError('Unsupported file type. Please upload a JPEG, PNG, WebP image or PDF.');
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }

    setUploading(true);
    try {
      const doc = await api.uploadDocument(sessionId, file, docType);
      setDocuments((prev) => [doc, ...prev]);
      onUploadComplete?.(doc);
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.code === 'DOCUMENT_CONSENT_REQUIRED') {
          setError('Document processing consent is required.');
        } else if (err.code === 'FILE_TOO_LARGE') {
          setError('Document exceeds the 10MB limit.');
        } else {
          setError(err.message || 'Failed to upload document.');
        }
      } else {
        setError('Network error uploading document.');
      }
    } finally {
      setUploading(false);
    }
  }

  if (!documentConsent) {
    return (
      <div className="document-uploader-disabled" data-testid="document-uploader-disabled">
        <p className="muted" style={{ fontStyle: 'italic' }}>
          Document upload is disabled because consent was not provided.
        </p>
      </div>
    );
  }

  return (
    <div className="document-uploader" data-testid="document-uploader">
      <div className="document-uploader-header">
        <h3>{t.docUploadTitle}</h3>
        <p className="muted">{t.docUploadSubtitle}</p>
      </div>

      <div className="document-immutability-notice" role="note">
        <span aria-hidden="true">ℹ️</span>
        <span>{t.docImmutabilityNotice}</span>
      </div>

      <div className="document-upload-controls">
        <div className="doc-type-selector">
          <label htmlFor="doc-type-select" className="sr-only">
            Document Type
          </label>
          <select
            id="doc-type-select"
            value={docType}
            onChange={(e) => setDocType(e.target.value as 'prescription' | 'lab_report' | 'other')}
            disabled={uploading}
          >
            <option value="prescription">{t.docPrescription}</option>
            <option value="lab_report">{t.docLabReport}</option>
            <option value="other">{t.docOther}</option>
          </select>
        </div>

        <input
          ref={fileInputRef}
          type="file"
          id="document-file-input"
          data-testid="document-file-input"
          accept="image/jpeg,image/png,image/webp,application/pdf"
          onChange={handleFileChange}
          style={{ display: 'none' }}
          disabled={uploading}
        />

        <button
          type="button"
          className="secondary"
          disabled={uploading}
          onClick={() => fileInputRef.current?.click()}
          data-testid="upload-document-btn"
        >
          {uploading ? t.docUploading : `📎 ${t.docUploadBtn}`}
        </button>
      </div>

      {error && (
        <p className="error" role="alert" style={{ marginTop: '0.5rem' }}>
          {error}
        </p>
      )}

      {documents.length > 0 && (
        <div className="uploaded-documents-list" data-testid="uploaded-documents-list">
          {documents.map((doc) => (
            <div key={doc.id} className="uploaded-document-card" data-testid={`doc-card-${doc.id}`}>
              <div className="doc-card-header">
                <div>
                  <strong className="doc-filename">{doc.original_filename}</strong>
                  <span className="doc-badge doc-type-badge">{doc.document_type}</span>
                </div>
                <span className={`doc-badge status-${doc.processing_status}`}>
                  {doc.processing_status}
                </span>
              </div>

              {doc.extractions && doc.extractions.length > 0 && (
                <div className="doc-extractions-summary">
                  {doc.extractions.map((ext) => {
                    const meds = ext.structured_json.medications;
                    const labs = ext.structured_json.observations;
                    return (
                      <div key={ext.id} className="extraction-content">
                        {ext.extractor === 'mock' && (
                          <p role="note">
                            Synthetic mock output. This is fixture data and may not describe the
                            uploaded record.
                          </p>
                        )}
                        <div className="extraction-meta">
                          <span className="badge-unverified">{t.docPendingVerification}</span>
                          {ext.extractor !== 'mock' && ext.confidence !== null && (
                            <span className="muted">
                              Confidence: {Math.round(ext.confidence * 100)}%
                            </span>
                          )}
                        </div>

                        {meds && meds.length > 0 && (
                          <div className="extracted-meds-list">
                            <strong>{t.docExtractedMedications}:</strong>
                            <ul>
                              {meds.map((m, idx) => (
                                <li key={idx}>
                                  <b>{m.name}</b> {m.dosage ? `· ${m.dosage}` : ''}{' '}
                                  {m.frequency ? `· ${m.frequency}` : ''}{' '}
                                  {m.duration ? `· ${m.duration}` : ''}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {labs && labs.length > 0 && (
                          <div className="extracted-labs-list">
                            <strong>{t.docExtractedLabs}:</strong>
                            <ul>
                              {labs.map((l, idx) => (
                                <li key={idx}>
                                  <b>{l.test_name}</b>: {l.value} {l.unit || ''}{' '}
                                  {l.reference_range ? `(${l.reference_range})` : ''}{' '}
                                  {l.flag && l.flag.toLowerCase() !== 'normal' ? (
                                    <span className="badge-abnormal">{l.flag.toUpperCase()}</span>
                                  ) : !l.flag ? (
                                    <span className="muted">Not reported</span>
                                  ) : null}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
              {doc.processing_status === 'unavailable' && doc.extractions.length === 0 && (
                <p className="muted" role="status">
                  The original file is stored, but extraction is unavailable. This prototype only
                  extracts its explicitly identified synthetic fixtures; real OCR is not enabled.
                </p>
              )}
              {doc.processing_status === 'failed' && (
                <p className="error" role="alert">
                  The original file was stored, but document processing failed. Clinical facts were
                  not created.
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
