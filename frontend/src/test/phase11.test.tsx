import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ABDMHISModal } from '../components/doctor/ABDMHISModal';
import { api } from '../api/client';
import type { ABDMStatusResponse } from '../api/client';

describe('Phase 11 ABDM & HIS Interoperability Components', () => {
  const sessionId = 'session-abdm-001';
  const mockInitialStatus: ABDMStatusResponse = {
    session_id: sessionId,
    patient_id: 'patient-001',
    abha_number: null,
    abha_address: 'patient@abdm',
    abha_status: 'mock_verified',
    care_context_reference: null,
    care_context_display: null,
    care_context_status: 'unlinked',
    care_context_linked_at: null,
    his_dispatch_status: 'not_dispatched',
    his_dispatch_receipt: null,
    his_dispatched_at: null,
    consent_artefact_id: null,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('ABDMHISModal', () => {
    it('fetches and renders ABDM and HIS status when opened', async () => {
      vi.spyOn(api, 'getAbdmStatus').mockResolvedValueOnce(mockInitialStatus);

      render(
        <ABDMHISModal
          isOpen={true}
          onClose={vi.fn()}
          sessionId={sessionId}
          patientName="Sunita Sharma"
          hospitalToken="HOSP-101"
          demoAbhaId="patient@abdm"
        />,
      );

      expect(screen.getByText('ABDM & HIS Interoperability Hub')).toBeInTheDocument();
      expect(screen.getByText('Sandbox Demonstration')).toBeInTheDocument();

      await waitFor(() => {
        expect(screen.getByTestId('abha-status-badge')).toHaveTextContent(
          '✓ Verified (Sandbox Mock)',
        );
        expect(screen.getByTestId('care-context-badge')).toHaveTextContent('Unlinked');
        expect(screen.getByTestId('his-status-badge')).toHaveTextContent('Not Dispatched');
      });
    });

    it('handles ABHA verification via mock gateway', async () => {
      vi.spyOn(api, 'getAbdmStatus').mockResolvedValue(mockInitialStatus);
      vi.spyOn(api, 'verifyDoctorAbha').mockResolvedValueOnce({
        success: true,
        profile: {
          abha_number: '91-1234-5678-9012',
          abha_address: 'sunita@abdm',
          name: 'Sunita Sharma',
          gender: 'Female',
          dob: '1988-04-12',
          mobile_masked: 'XXXXXX9012',
          status: 'mock_verified',
        },
        message: 'ABHA verified successfully',
      });

      render(
        <ABDMHISModal
          isOpen={true}
          onClose={vi.fn()}
          sessionId={sessionId}
          patientName="Sunita Sharma"
          hospitalToken="HOSP-101"
          demoAbhaId="patient@abdm"
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId('doctor-verify-abha-btn')).toBeInTheDocument();
      });

      fireEvent.change(screen.getByTestId('abha-input'), { target: { value: 'sunita@abdm' } });
      fireEvent.click(screen.getByTestId('doctor-verify-abha-btn'));

      await waitFor(() => {
        expect(api.verifyDoctorAbha).toHaveBeenCalledWith(sessionId, 'sunita@abdm');
        expect(screen.getByTestId('verify-message')).toHaveTextContent(
          '✓ ABHA verified: Sunita Sharma (91-1234-5678-9012)',
        );
      });
    });

    it('links care context (M2)', async () => {
      vi.spyOn(api, 'getAbdmStatus').mockResolvedValue(mockInitialStatus);
      vi.spyOn(api, 'linkCareContext').mockResolvedValueOnce({
        success: true,
        care_context_reference: 'medikiosk_ctx_test123',
        display: 'MediKiosk OPD Intake - Token HOSP-101',
        status: 'linked',
        linked_at: '2026-09-10T12:00:00Z',
        message: 'Care context linked successfully',
      });

      render(
        <ABDMHISModal
          isOpen={true}
          onClose={vi.fn()}
          sessionId={sessionId}
          patientName="Sunita Sharma"
          hospitalToken="HOSP-101"
          demoAbhaId="patient@abdm"
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId('link-care-context-btn')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId('link-care-context-btn'));

      await waitFor(() => {
        expect(api.linkCareContext).toHaveBeenCalledWith(sessionId);
        expect(screen.getByTestId('link-message')).toHaveTextContent(
          '✓ Linked care context: medikiosk_ctx_test123',
        );
      });
    });

    it('dispatches to hospital HIS and renders receipt', async () => {
      vi.spyOn(api, 'getAbdmStatus').mockResolvedValue(mockInitialStatus);
      vi.spyOn(api, 'dispatchHis').mockResolvedValueOnce({
        success: true,
        dispatch_id: 'disp-001',
        target_endpoint: 'http://local-his.hospital.internal/api/v1/opd-intake',
        status: 'dispatched',
        dispatched_at: '2026-09-10T12:00:00Z',
        receipt_reference: 'HIS-ACK-20260910-ABCD1234',
        message: 'Dispatched successfully',
        attached_bundle_type: 'document',
      });

      render(
        <ABDMHISModal
          isOpen={true}
          onClose={vi.fn()}
          sessionId={sessionId}
          patientName="Sunita Sharma"
          hospitalToken="HOSP-101"
          demoAbhaId="patient@abdm"
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId('dispatch-his-btn')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId('dispatch-his-btn'));

      await waitFor(() => {
        expect(api.dispatchHis).toHaveBeenCalledWith(sessionId, 'Central Hospital OPD HIS');
        expect(screen.getByTestId('dispatch-message')).toHaveTextContent(
          'HIS-ACK-20260910-ABCD1234',
        );
      });
    });

    it('calls onClose when close button is clicked', async () => {
      vi.spyOn(api, 'getAbdmStatus').mockResolvedValue(mockInitialStatus);
      const onCloseMock = vi.fn();

      render(
        <ABDMHISModal
          isOpen={true}
          onClose={onCloseMock}
          sessionId={sessionId}
          patientName="Sunita Sharma"
          hospitalToken="HOSP-101"
        />,
      );

      fireEvent.click(screen.getByTestId('close-abdm-modal-btn'));
      expect(onCloseMock).toHaveBeenCalled();
    });
  });
});
