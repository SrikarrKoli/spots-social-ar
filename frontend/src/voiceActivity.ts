// Silence ends a turn only after sustained speech. No-speech turns are discarded.
export class VoiceActivity {
  private speechMs = 0;
  private lastVoiceAt = 0;
  private previousAt: number;
  heardSpeech = false;
  constructor(private startedAt: number) { this.previousAt = startedAt; }
  update(rms: number, now: number): "speech_end" | "no_speech" | null {
    const elapsed = Math.min(100, Math.max(0, now - this.previousAt));
    this.previousAt = now;
    if (rms > 0.018) {
      this.speechMs += elapsed;
      this.lastVoiceAt = now;
      if (this.speechMs >= 220) this.heardSpeech = true;
    }
    if (this.heardSpeech && (now - this.lastVoiceAt > 1200 || now - this.startedAt > 25000)) return "speech_end";
    if (!this.heardSpeech && now - this.startedAt > 10000) return "no_speech";
    return null;
  }
}
