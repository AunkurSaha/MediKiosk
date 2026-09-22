import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { HospitalSelection } from '../routes/kiosk';

it('renders hospitals and requires an explicit visit selection', () => {
  const select = vi.fn();
  render(
    <HospitalSelection
      hospitals={[{ id: 'h1', name: 'City Hospital', city: 'Kolkata', address: 'Central Kolkata' }]}
      load={vi.fn()}
      busy={false}
      onSelect={select}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: /City Hospital/ }));
  expect(select).toHaveBeenCalledWith('h1');
});

it('shows loading, empty, and retryable failure states', async () => {
  const loading = render(
    <HospitalSelection
      hospitals={null}
      load={vi.fn().mockResolvedValue(undefined)}
      busy={false}
      onSelect={vi.fn()}
    />,
  );
  expect(screen.getByRole('status')).toHaveTextContent('Loading hospitals');
  loading.unmount();
  const empty = render(
    <HospitalSelection hospitals={[]} load={vi.fn()} busy={false} onSelect={vi.fn()} />,
  );
  expect(screen.getByText(/No hospitals/)).toBeInTheDocument();
  empty.unmount();
  const failing = vi.fn().mockRejectedValue(new Error('offline'));
  render(<HospitalSelection hospitals={null} load={failing} busy={false} onSelect={vi.fn()} />);
  await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
});
