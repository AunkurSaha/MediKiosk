import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import Kiosk from '../routes/kiosk';
import Doctor from '../routes/doctor';
import { api } from '../api/client';
import type { Detail, SessionList } from '../api/client';

describe('Phase 12 Demo Polish & Showcase Seeding Components', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      value: null,
    });
    Object.defineProperty(document.documentElement, 'requestFullscreen', {
      configurable: true,
      value: vi.fn(async () => {
        Object.defineProperty(document, 'fullscreenElement', {
          configurable: true,
          value: document.documentElement,
        });
        document.dispatchEvent(new Event('fullscreenchange'));
      }),
    });
    Object.defineProperty(document, 'exitFullscreen', {
      configurable: true,
      value: vi.fn(async () => {
        Object.defineProperty(document, 'fullscreenElement', {
          configurable: true,
          value: null,
        });
        document.dispatchEvent(new Event('fullscreenchange'));
      }),
    });
  });

  describe('Kiosk Demo Polish', () => {
    it('renders fullscreen button and does not expose showcase loader on patient kiosk', () => {
      render(
        <MemoryRouter initialEntries={['/kiosk/language']}>
          <Routes>
            <Route path="/kiosk/*" element={<Kiosk />} />
          </Routes>
        </MemoryRouter>,
      );

      const fullscreenBtn = screen.getByTestId('kiosk-fullscreen-btn');
      expect(fullscreenBtn).toBeInTheDocument();
      expect(fullscreenBtn).toHaveTextContent('Fullscreen');
      expect(screen.queryByTestId('kiosk-load-showcase-btn')).not.toBeInTheDocument();
    });

    it('toggles fullscreen button label and follows fullscreenchange', async () => {
      render(
        <MemoryRouter initialEntries={['/kiosk/language']}>
          <Routes>
            <Route path="/kiosk/*" element={<Kiosk />} />
          </Routes>
        </MemoryRouter>,
      );

      const fullscreenBtn = screen.getByTestId('kiosk-fullscreen-btn');
      expect(fullscreenBtn).toHaveTextContent('Fullscreen');
      fireEvent.click(fullscreenBtn);
      await waitFor(() => expect(fullscreenBtn).toHaveTextContent('Exit Fullscreen'));
      fireEvent.click(fullscreenBtn);
      await waitFor(() => expect(fullscreenBtn).toHaveTextContent('Fullscreen'));
    });

    it('shows a visible fallback when fullscreen fails', async () => {
      vi.mocked(document.documentElement.requestFullscreen).mockRejectedValueOnce(
        new Error('denied'),
      );
      render(
        <MemoryRouter initialEntries={['/kiosk/language']}>
          <Routes>
            <Route path="/kiosk/*" element={<Kiosk />} />
          </Routes>
        </MemoryRouter>,
      );

      fireEvent.click(screen.getByTestId('kiosk-fullscreen-btn'));
      expect(
        await screen.findByText(
          'Fullscreen could not be changed. Try the browser controls instead.',
        ),
      ).toBeInTheDocument();
    });
  });

  describe('Doctor Workspace Demo Polish', () => {
    const mockSessionList: SessionList = {
      items: [
        {
          id: 'session-showcase-101',
          patient_id: 'patient-showcase-101',
          patient_name: 'Sunita Sharma (সুমিতা শর্মা)',
          hospital_token: 'T-SHOWCASE-101',
          language: 'bn',
          status: 'ready_for_review',
          created_at: new Date().toISOString(),
          completed_at: null,
        },
      ],
    };

    it('renders Seed Showcase and Reset Demo buttons on Doctor overview', async () => {
      vi.spyOn(api, 'sessions').mockResolvedValueOnce(mockSessionList);

      render(
        <MemoryRouter initialEntries={['/doctor']}>
          <Routes>
            <Route path="/doctor" element={<Doctor />} />
          </Routes>
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('seed-showcase-btn')).toBeInTheDocument();
        expect(screen.getByTestId('reset-demo-btn')).toBeInTheDocument();
        expect(screen.getByText('Sunita Sharma (সুমিতা শর্মা)')).toBeInTheDocument();
      });
    });

    it('calls seedShowcase API when clicking Seed Showcase button', async () => {
      vi.spyOn(api, 'sessions').mockResolvedValue(mockSessionList);
      vi.spyOn(api, 'seedShowcase').mockResolvedValueOnce({
        session_id: 'session-showcase-101',
        patient_name: 'Sunita Sharma (সুমিতা শর্মা)',
        hospital_token: 'T-SHOWCASE-101',
        language: 'bn',
        status: 'ready_for_review',
        summary_id: 'sum-101',
        message: 'Showcase seeded',
      });

      render(
        <MemoryRouter initialEntries={['/doctor']}>
          <Routes>
            <Route path="/doctor" element={<Doctor />} />
          </Routes>
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('seed-showcase-btn')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId('seed-showcase-btn'));

      await waitFor(() => {
        expect(api.seedShowcase).toHaveBeenCalledTimes(1);
        expect(screen.getByText(/Showcase patient Sunita Sharma/i)).toBeInTheDocument();
      });
    });

    it('calls resetDemo API when clicking Reset Demo button with confirm', async () => {
      vi.spyOn(api, 'sessions').mockResolvedValue(mockSessionList);
      vi.spyOn(api, 'resetDemo').mockResolvedValueOnce({
        success: true,
        message: 'Demo data reset successfully.',
      });
      vi.spyOn(window, 'confirm').mockReturnValue(true);

      render(
        <MemoryRouter initialEntries={['/doctor']}>
          <Routes>
            <Route path="/doctor" element={<Doctor />} />
          </Routes>
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('reset-demo-btn')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId('reset-demo-btn'));

      await waitFor(() => {
        expect(api.resetDemo).toHaveBeenCalledTimes(1);
        expect(screen.getByText('Demo data reset successfully.')).toBeInTheDocument();
      });
    });

    it('renders emergency triage alerts with high-visibility pulsing style', async () => {
      const mockEmergencyDetail: Detail = {
        session: {
          id: 'session-emergency-001',
          patient_id: 'patient-001',
          hospital_token: 'T-SHOWCASE-101',
          language: 'bn',
          status: 'ready_for_review',
          created_at: new Date().toISOString(),
          completed_at: null,
        },
        patient: {
          id: 'patient-001',
          name: 'Sunita Sharma (সুমিতা শর্মা)',
          demo_abha_id: 'patient@abdm',
        },
        consent: {
          share_with_doctor: true,
          voice_processing: true,
          document_processing: true,
        },
        answers: [],
        alerts: [
          {
            id: 'alert-em-001',
            session_id: 'session-emergency-001',
            rule_id: 'RF-CHEST-001',
            rule_version: '1.0.1',
            priority: 'emergency',
            category: 'cardiovascular',
            reason: 'Reported chest pain severity at least 8/10 with radiation to left arm.',
            triggering_facts: [],
            status: 'new',
            revision: 0,
            acknowledged_at: null,
            acknowledged_by: null,
            acknowledgement_note: null,
            created_at: new Date().toISOString(),
            updated_at: null,
            hospital_token: 'T-SHOWCASE-101',
            patient_name: 'Sunita Sharma (সুমিতা শর্মা)',
          },
        ],
        documents: [],
        summary: null,
      };

      vi.spyOn(api, 'doctorDetail').mockResolvedValueOnce(mockEmergencyDetail);

      render(
        <MemoryRouter initialEntries={['/doctor/sessions/session-emergency-001']}>
          <Routes>
            <Route path="/doctor/sessions/:sessionId" element={<Doctor />} />
          </Routes>
        </MemoryRouter>,
      );

      await waitFor(() => {
        const banner = screen.getByTestId('doctor-alerts-banner');
        expect(banner).toBeInTheDocument();
        expect(screen.getByText('🚨 EMERGENCY')).toBeInTheDocument();
        expect(
          screen.getByText(
            /Reported chest pain severity at least 8\/10 with radiation to left arm/,
          ),
        ).toBeInTheDocument();
      });
    });
  });
});
