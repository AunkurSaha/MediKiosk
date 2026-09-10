import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { FHIRExportModal } from '../components/doctor/FHIRExportModal';
import { api } from '../api/client';
import type { FHIRExportResponse } from '../api/client';

describe('Phase 10 FHIR R4 Export Architecture Components', () => {
  const sessionId = 'session-fhir-001';
  const mockExportData: FHIRExportResponse = {
    session_id: sessionId,
    bundle_type: 'document',
    compliance_profile: 'HL7 FHIR R4 / NRCES EHR Profile',
    generated_at: '2026-09-10T12:00:00Z',
    resource_counts: {
      Patient: 1,
      Encounter: 1,
      Composition: 1,
      QuestionnaireResponse: 1,
      Condition: 1,
      MedicationStatement: 1,
      Observation: 1,
      DocumentReference: 1,
    },
    validation: {
      resourceType: 'OperationOutcome',
      issue: [],
    },
    bundle: {
      resourceType: 'Bundle',
      id: `bundle-${sessionId}`,
      type: 'document',
      timestamp: '2026-09-10T12:00:00Z',
      entry: [
        {
          fullUrl: `urn:uuid:comp-1`,
          resource: {
            resourceType: 'Composition',
            id: 'comp-1',
            status: 'final',
          },
        },
        {
          fullUrl: `urn:uuid:patient-1`,
          resource: {
            resourceType: 'Patient',
            id: 'patient-1',
            name: [{ text: 'Sunita Sharma' }],
          },
        },
      ],
    },
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('FHIRExportModal', () => {
    it('fetches and renders FHIR export data when opened', async () => {
      vi.spyOn(api, 'getFhirExport').mockResolvedValueOnce(mockExportData);

      render(
        <FHIRExportModal
          isOpen={true}
          onClose={vi.fn()}
          sessionId={sessionId}
          patientName="Sunita Sharma"
          hospitalToken="HOSP-101"
        />
      );

      expect(screen.getByText('HL7 FHIR R4 Bundle Export')).toBeInTheDocument();
      expect(screen.getByText(/Sunita Sharma/)).toBeInTheDocument();

      await waitFor(() => {
        expect(api.getFhirExport).toHaveBeenCalledWith(sessionId, 'document');
        expect(screen.getByText('HL7 FHIR R4 Conformance Validated')).toBeInTheDocument();
        expect(screen.getByText('Total Entries:')).toBeInTheDocument();
        expect(screen.getByText('Composition:')).toBeInTheDocument();
        expect(screen.getByText('Patient:')).toBeInTheDocument();
        expect(screen.getByTestId('fhir-json-preview')).toBeInTheDocument();
      });

      // Safety guardrail note is displayed
      expect(screen.getByText(/Non-Diagnostic Boundary:/i)).toBeInTheDocument();
    });

    it('toggles bundle format to collection and refetches', async () => {
      vi.spyOn(api, 'getFhirExport')
        .mockResolvedValueOnce(mockExportData)
        .mockResolvedValueOnce({
          ...mockExportData,
          bundle_type: 'collection',
          bundle: { ...mockExportData.bundle, type: 'collection' },
        });

      render(
        <FHIRExportModal
          isOpen={true}
          onClose={vi.fn()}
          sessionId={sessionId}
          patientName="Sunita Sharma"
          hospitalToken="HOSP-101"
        />
      );

      await waitFor(() => {
        expect(api.getFhirExport).toHaveBeenCalledWith(sessionId, 'document');
      });

      const collectionBtn = screen.getByRole('button', { name: /Collection \(Flat\)/i });
      fireEvent.click(collectionBtn);

      await waitFor(() => {
        expect(api.getFhirExport).toHaveBeenCalledWith(sessionId, 'collection');
      });
    });

    it('copies JSON to clipboard on button click', async () => {
      vi.spyOn(api, 'getFhirExport').mockResolvedValueOnce(mockExportData);
      const writeTextMock = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, {
        clipboard: { writeText: writeTextMock },
      });

      render(
        <FHIRExportModal
          isOpen={true}
          onClose={vi.fn()}
          sessionId={sessionId}
          patientName="Sunita Sharma"
          hospitalToken="HOSP-101"
        />
      );

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /📋 Copy JSON/i })).toBeInTheDocument();
      });

      const copyBtn = screen.getByRole('button', { name: /📋 Copy JSON/i });
      fireEvent.click(copyBtn);

      await waitFor(() => {
        expect(writeTextMock).toHaveBeenCalledWith(
          JSON.stringify(mockExportData.bundle, null, 2)
        );
        expect(screen.getByText('✓ Copied!')).toBeInTheDocument();
      });
    });

    it('downloads JSON file when download button is clicked', async () => {
      vi.spyOn(api, 'getFhirExport').mockResolvedValueOnce(mockExportData);
      const createObjectURLMock = vi.fn().mockReturnValue('blob:http://localhost/mock-blob');
      const revokeObjectURLMock = vi.fn();
      globalThis.URL.createObjectURL = createObjectURLMock;
      globalThis.URL.revokeObjectURL = revokeObjectURLMock;

      render(
        <FHIRExportModal
          isOpen={true}
          onClose={vi.fn()}
          sessionId={sessionId}
          patientName="Sunita Sharma"
          hospitalToken="HOSP-101"
        />
      );

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /⬇ Download JSON/i })).toBeInTheDocument();
      });

      const downloadBtn = screen.getByRole('button', { name: /⬇ Download JSON/i });
      fireEvent.click(downloadBtn);

      expect(createObjectURLMock).toHaveBeenCalled();
      expect(revokeObjectURLMock).toHaveBeenCalledWith('blob:http://localhost/mock-blob');
    });

    it('displays error message when export fails', async () => {
      vi.spyOn(api, 'getFhirExport').mockRejectedValueOnce(new Error('Network error loading bundle'));

      render(
        <FHIRExportModal
          isOpen={true}
          onClose={vi.fn()}
          sessionId={sessionId}
          patientName="Sunita Sharma"
          hospitalToken="HOSP-101"
        />
      );

      await waitFor(() => {
        expect(screen.getByText(/Network error loading bundle/i)).toBeInTheDocument();
      });
    });

    it('calls onClose when close button is clicked', () => {
      const onClose = vi.fn();
      render(
        <FHIRExportModal
          isOpen={true}
          onClose={onClose}
          sessionId={sessionId}
          patientName="Sunita Sharma"
          hospitalToken="HOSP-101"
        />
      );

      const closeButtons = screen.getAllByRole('button', { name: /close/i });
      fireEvent.click(closeButtons[0]);
      expect(onClose).toHaveBeenCalled();
    });
  });
});
