const TARGET_SAMPLE_RATE = 16_000;

function abortIfRequested(signal?: AbortSignal) {
  if (signal?.aborted) throw new DOMException('Audio conversion was cancelled.', 'AbortError');
}

export function createPcm16Wav(
  channels: readonly Float32Array[],
  sourceSampleRate: number,
): ArrayBuffer {
  if (!channels.length || !channels[0].length || sourceSampleRate <= 0) {
    throw new Error('Decoded audio is empty or invalid.');
  }
  const sourceLength = channels[0].length;
  if (channels.some((channel) => channel.length !== sourceLength)) {
    throw new Error('Decoded audio channels have inconsistent lengths.');
  }

  const sampleCount = Math.max(
    1,
    Math.round((sourceLength * TARGET_SAMPLE_RATE) / sourceSampleRate),
  );
  const buffer = new ArrayBuffer(44 + sampleCount * 2);
  const view = new DataView(buffer);
  const writeText = (offset: number, value: string) => {
    for (let index = 0; index < value.length; index++) {
      view.setUint8(offset + index, value.charCodeAt(index));
    }
  };

  writeText(0, 'RIFF');
  view.setUint32(4, 36 + sampleCount * 2, true);
  writeText(8, 'WAVE');
  writeText(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, TARGET_SAMPLE_RATE, true);
  view.setUint32(28, TARGET_SAMPLE_RATE * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeText(36, 'data');
  view.setUint32(40, sampleCount * 2, true);

  for (let targetIndex = 0; targetIndex < sampleCount; targetIndex++) {
    const sourcePosition = (targetIndex * sourceSampleRate) / TARGET_SAMPLE_RATE;
    const lower = Math.min(Math.floor(sourcePosition), sourceLength - 1);
    const upper = Math.min(lower + 1, sourceLength - 1);
    const mix = sourcePosition - lower;
    let mono = 0;
    for (const channel of channels) {
      mono += channel[lower] + (channel[upper] - channel[lower]) * mix;
    }
    mono = Math.max(-1, Math.min(1, mono / channels.length));
    view.setInt16(44 + targetIndex * 2, mono < 0 ? mono * 0x8000 : mono * 0x7fff, true);
  }
  return buffer;
}

export async function convertRecordedAudioToWav(
  recording: Blob,
  signal?: AbortSignal,
): Promise<Blob> {
  abortIfRequested(signal);
  const encoded = await recording.arrayBuffer();
  abortIfRequested(signal);
  const context = new AudioContext();
  try {
    const decoded = await context.decodeAudioData(encoded);
    abortIfRequested(signal);
    const channels = Array.from({ length: decoded.numberOfChannels }, (_, index) =>
      decoded.getChannelData(index),
    );
    return new Blob([createPcm16Wav(channels, decoded.sampleRate)], { type: 'audio/wav' });
  } finally {
    await context.close();
  }
}
