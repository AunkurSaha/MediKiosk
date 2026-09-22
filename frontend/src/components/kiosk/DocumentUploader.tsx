import { useCallback, useEffect, useRef, useState } from 'react';
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
  const [dismissedDocuments, setDismissedDocuments] = useState<Set<string>>(new Set());
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [docType, setDocType] = useState<'prescription' | 'lab_report' | 'other'>('prescription');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [cameraOpen, setCameraOpen] = useState(false);
  const [cameraReady, setCameraReady] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    setCameraReady(false);
    setCameraOpen(false);
  }, []);

  useEffect(() => {
    const video = videoRef.current;
    const stream = streamRef.current;
    if (!cameraOpen || !video || !stream) return;

    video.srcObject = stream;
    void video.play().catch(() => {
      setError('Camera preview could not start. Please close the camera and try again.');
    });

    return () => {
      if (video.srcObject === stream) video.srcObject = null;
    };
  }, [cameraOpen]);

  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, [stopCamera]);

  const startCamera = async () => {
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        setError('Camera access is not supported in this browser.');
        return;
      }
      setCameraReady(false);
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
      });
      streamRef.current = stream;
      setCameraOpen(true);
      setError(null);
    } catch {
      setError('Unable to access camera. Please ensure permissions are granted.');
    }
  };

  const capturePhoto = () => {
    if (videoRef.current && canvasRef.current) {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      if (!cameraReady || video.videoWidth === 0 || video.videoHeight === 0) {
        setError('Camera is still starting. Please wait for the preview before capturing.');
        return;
      }
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext('2d');
      if (ctx) {
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        canvas.toBlob(
          async (blob) => {
            if (blob) {
              const file = new File([blob], 'camera-capture.jpg', { type: 'image/jpeg' });
              stopCamera();
              await uploadFile(file);
            }
          },
          'image/jpeg',
          0.8,
        );
      }
    }
  };

  // Load any previously uploaded documents for this session
  useEffect(() => {
    let active = true;
    if (!documentConsent) return;
    api
      .documents(sessionId)
      .then((res) => {
        if (active) {
          setDocuments((prev) => {
            const fetchedIds = new Set(res.documents.map((d) => d.id));
            const pendingOrLocal = prev.filter((d) => !fetchedIds.has(d.id));
            return [...pendingOrLocal, ...res.documents];
          });
        }
      })
      .catch(() => {
        // Silently tolerate list failure on load
      });
    return () => {
      active = false;
    };
  }, [sessionId, documentConsent]);

  async function uploadFile(file: File) {
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

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    await uploadFile(file);
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
        <p className="eyebrow">Medical records</p>
        <h3>Upload a medical document</h3>
        <p className="muted">
          Add a clear photo or PDF. You will review every detail before it becomes part of your
          history.
        </p>
        <div className="document-supported-types" aria-label="Supported documents">
          <span>Prescription</span>
          <span>Lab report</span>
          <span>Discharge document</span>
        </div>
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
          {uploading ? 'Analyzing document…' : t.docUploadBtn}
        </button>

        <button
          type="button"
          className="secondary"
          disabled={uploading || cameraOpen}
          onClick={startCamera}
          style={{ marginLeft: '1rem' }}
          data-testid="open-camera-btn"
        >
          Use camera
        </button>
      </div>

      {cameraOpen && (
        <div
          className="camera-container"
          style={{
            marginTop: '1rem',
            border: '1px solid var(--border-subtle)',
            padding: '1rem',
            borderRadius: '8px',
          }}
        >
          <video
            ref={videoRef}
            autoPlay
            muted
            playsInline
            onLoadedMetadata={() => setCameraReady(true)}
            style={{
              width: '100%',
              maxHeight: '400px',
              objectFit: 'contain',
              backgroundColor: '#000',
              borderRadius: '4px',
            }}
          />
          <canvas ref={canvasRef} style={{ display: 'none' }} />
          <div
            style={{ marginTop: '1rem', display: 'flex', gap: '1rem', justifyContent: 'center' }}
          >
            <button
              type="button"
              onClick={capturePhoto}
              className="primary"
              disabled={!cameraReady || uploading}
            >
              {cameraReady ? '📸 Capture Image' : 'Starting camera…'}
            </button>
            <button type="button" onClick={stopCamera} className="secondary">
              Cancel
            </button>
          </div>
        </div>
      )}

      {error && (
        <div className="error document-upload-error" role="alert">
          <strong>We could not process this document.</strong>
          <p>{error}</p>
          <div className="inline-actions">
            <button
              type="button"
              className="secondary"
              onClick={() => fileInputRef.current?.click()}
            >
              Try another file
            </button>
            <button type="button" className="text-button" onClick={() => setError(null)}>
              Skip for now
            </button>
          </div>
        </div>
      )}

      {uploading && (
        <p className="document-analysis-state" role="status">
          Analyzing document…
        </p>
      )}

      {documents.length > 0 && (
        <div className="uploaded-documents-list" data-testid="uploaded-documents-list">
          {documents
            .filter((doc) => !dismissedDocuments.has(doc.id))
            .map((doc) => (
              <div
                key={doc.id}
                className="uploaded-document-card"
                data-testid={`doc-card-${doc.id}`}
              >
                <div className="doc-card-header">
                  <div>
                    <strong className="doc-filename">{doc.original_filename}</strong>
                    <span className="doc-badge doc-type-badge">{doc.document_type}</span>
                  </div>
                  <span className={`doc-badge status-${doc.processing_status}`}>
                    {doc.processing_status === 'mock_fixture' ||
                    doc.processing_status === 'completed'
                      ? 'Information extracted'
                      : doc.processing_status === 'processing'
                        ? 'Analyzing'
                        : doc.processing_status === 'unavailable'
                          ? 'Review needed'
                          : doc.processing_status}
                  </span>
                </div>

                {doc.extractions && doc.extractions.length > 0 && (
                  <div className="doc-extractions-summary">
                    {doc.extractions.map((ext) => {
                      const meds = ext.structured_json.medications;
                      const labs = ext.structured_json.observations;
                      const details = ext.structured_json as typeof ext.structured_json & {
                        patient_name?: string;
                        patient_age?: string;
                        patient_weight?: string;
                        complaint?: string;
                        advice?: string[];
                      };
                      return (
                        <div key={ext.id} className="extraction-content">
                          <div className="extraction-meta">
                            <div>
                              <p className="eyebrow">Document information extracted</p>
                              <h4>
                                {doc.document_type === 'prescription'
                                  ? 'Information found in your prescription'
                                  : 'Information found in your report'}
                              </h4>
                            </div>
                            <span className="badge-unverified">Needs your review</span>
                            {ext.extractor !== 'mock' && ext.confidence !== null && (
                              <span className="muted">
                                Confidence: {Math.round(ext.confidence * 100)}%
                              </span>
                            )}
                          </div>

                          {(details.patient_name || details.complaint) && (
                            <div className="document-context-grid">
                              {details.patient_name && (
                                <div>
                                  <span>Patient</span>
                                  <strong>{details.patient_name}</strong>
                                </div>
                              )}
                              {details.patient_age && (
                                <div>
                                  <span>Age</span>
                                  <strong>{details.patient_age}</strong>
                                </div>
                              )}
                              {details.patient_weight && (
                                <div>
                                  <span>Weight</span>
                                  <strong>{details.patient_weight}</strong>
                                </div>
                              )}
                              {details.complaint && (
                                <div className="wide">
                                  <span>Reason noted</span>
                                  <strong>{details.complaint}</strong>
                                </div>
                              )}
                            </div>
                          )}

                          {meds && meds.length > 0 && (
                            <div className="extracted-meds-list extracted-information-grid">
                              {meds.map((m, idx) => (
                                <article key={idx} className="extracted-information-card">
                                  <div>
                                    <span>Medication</span>
                                    <strong>{m.name}</strong>
                                  </div>
                                  <div>
                                    <span>Strength</span>
                                    <strong>{m.dosage || 'Not stated'}</strong>
                                  </div>
                                  <div>
                                    <span>How often</span>
                                    <strong>{m.frequency || 'Not stated'}</strong>
                                  </div>
                                  <div>
                                    <span>Duration</span>
                                    <strong>{m.duration || 'Not stated'}</strong>
                                  </div>
                                  {m.instructions && (
                                    <div className="wide">
                                      <span>Instructions</span>
                                      <strong>{m.instructions}</strong>
                                    </div>
                                  )}
                                </article>
                              ))}
                            </div>
                          )}

                          {labs && labs.length > 0 && (
                            <div className="extracted-labs-list extracted-information-grid">
                              {labs.map((l, idx) => (
                                <article
                                  key={idx}
                                  className="extracted-information-card lab-result-card"
                                >
                                  <div>
                                    <span>Test</span>
                                    <strong>{l.test_name}</strong>
                                  </div>
                                  <div>
                                    <span>Result</span>
                                    <strong>
                                      {l.value} {l.unit || ''}
                                    </strong>
                                  </div>
                                  <div className="wide">
                                    <span>Reference range</span>
                                    <strong>{l.reference_range || 'Not stated'}</strong>
                                  </div>
                                  {l.flag && l.flag.toLowerCase() !== 'normal' ? (
                                    <span className="badge-abnormal">{l.flag.toUpperCase()}</span>
                                  ) : null}
                                </article>
                              ))}
                            </div>
                          )}

                          {details.advice && details.advice.length > 0 && (
                            <div className="extracted-advice">
                              <strong>Advice written on the document</strong>
                              <ul>
                                {details.advice.map((item) => (
                                  <li key={item}>{item}</li>
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
                  <div className="document-recovery" role="status">
                    <p className="muted">
                      We stored the original file, but could not extract information from it. Try a
                      clearer image or continue without document extraction.
                    </p>
                    <div className="inline-actions">
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => fileInputRef.current?.click()}
                      >
                        Replace file
                      </button>
                      <button
                        type="button"
                        className="text-button"
                        onClick={() =>
                          setDismissedDocuments((current) => new Set(current).add(doc.id))
                        }
                      >
                        Continue without this document
                      </button>
                    </div>
                  </div>
                )}
                {doc.processing_status === 'failed' && (
                  <p className="error" role="alert">
                    The original file was stored, but document processing failed. Clinical facts
                    were not created.
                  </p>
                )}
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
