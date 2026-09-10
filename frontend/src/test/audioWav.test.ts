import { describe, expect, it } from 'vitest';
import { createPcm16Wav } from '../utils/audioWav';

describe('browser recording PCM conversion', () => {
  it('downmixes and resamples to a 16 kHz mono 16-bit PCM WAV', () => {
    const wav = createPcm16Wav(
      [new Float32Array([1, 0.5, 0, -0.5]), new Float32Array([0, 0.5, 0, -0.5])],
      8_000,
    );
    const view = new DataView(wav);
    const text = (offset: number, length: number) =>
      String.fromCharCode(...new Uint8Array(wav, offset, length));

    expect(text(0, 4)).toBe('RIFF');
    expect(text(8, 4)).toBe('WAVE');
    expect(view.getUint16(20, true)).toBe(1);
    expect(view.getUint16(22, true)).toBe(1);
    expect(view.getUint32(24, true)).toBe(16_000);
    expect(view.getUint16(34, true)).toBe(16);
    expect(view.getUint32(40, true)).toBe(16);
    expect(wav.byteLength).toBe(60);
  });

  it('rejects empty or inconsistent decoded audio', () => {
    expect(() => createPcm16Wav([], 48_000)).toThrow();
    expect(() =>
      createPcm16Wav([new Float32Array([0]), new Float32Array([0, 1])], 48_000),
    ).toThrow();
  });
});
