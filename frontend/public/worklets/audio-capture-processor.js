/**
 * AudioWorklet processor — captures mic input, downsamples to 16 kHz mono,
 * buffers 250 ms of Int16 PCM, and posts the chunk to the main thread.
 *
 * Registered as: 'audio-capture-processor'
 */
class AudioCaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const targetRate = options.processorOptions?.targetSampleRate || 16000;
    this.ratio = sampleRate / targetRate;
    this.targetBufferSize = Math.floor(targetRate * 0.25); // 250 ms
    this.buffer = new Float32Array(this.targetBufferSize);
    this.writeIndex = 0;
    this.fractional = 0;
  }

  process(inputs) {
    const chan = inputs[0]?.[0];
    if (!chan) return true;

    for (let i = 0; i < chan.length; i++) {
      this.fractional += 1;
      if (this.fractional >= this.ratio) {
        this.fractional -= this.ratio;
        this.buffer[this.writeIndex++] = Math.max(-1, Math.min(1, chan[i]));

        if (this.writeIndex >= this.targetBufferSize) {
          const pcm = new Int16Array(this.targetBufferSize);
          for (let j = 0; j < this.targetBufferSize; j++) {
            pcm[j] = Math.round(this.buffer[j] * 32767);
          }
          this.port.postMessage({ type: 'chunk', pcm: pcm.buffer }, [pcm.buffer]);
          this.buffer = new Float32Array(this.targetBufferSize);
          this.writeIndex = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor('audio-capture-processor', AudioCaptureProcessor);
