import { Mic, MicOff, PhoneOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useVoiceClient } from "@/hooks/use-voice-client";
import { AudioVisualizer } from "./AudioVisualizer";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/*  Sentiment badge                                                    */
/* ------------------------------------------------------------------ */
function SentimentBadge({ value }: { value: string }) {
  const map: Record<string, { bg: string; label: string }> = {
    positive: { bg: "bg-emerald-500/20 text-emerald-400", label: "Positive" },
    negative: { bg: "bg-rose-500/20 text-rose-400", label: "Negative" },
    neutral:  { bg: "bg-zinc-500/20 text-zinc-400", label: "Neutral" },
  };
  const s = map[value] ?? map.neutral;
  return (
    <span className={cn("px-3 py-1 rounded-full text-xs font-medium", s.bg)}>
      {s.label}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/*  Main component                                                     */
/* ------------------------------------------------------------------ */
export function VoiceClient() {
  const {
    isConnected,
    isRecording,
    callActive,
    error,
    metadata,
    transcript,
    startCall,
    stopCall,
    analyserNode,
  } = useVoiceClient();

  return (
    <div className="w-full max-w-lg mx-auto select-none">
      {/* ---- Glass card ---- */}
      <div
        className={cn(
          "relative rounded-3xl border border-white/10 p-8",
          "bg-white/5 backdrop-blur-xl shadow-2xl",
          "flex flex-col items-center gap-6 transition-all duration-500",
          callActive && "ring-1 ring-cyan-500/30 shadow-cyan-500/10",
        )}
      >
        {/* ---- Visualizer ---- */}
        <AudioVisualizer
          analyser={analyserNode.current}
          isActive={isRecording}
        />

        {/* ---- Mic button ---- */}
        <div className="relative flex items-center justify-center">
          {/* pulse ring when recording */}
          {isRecording && (
            <span className="absolute inset-0 rounded-full animate-[voicePulse_2s_ease-in-out_infinite] bg-cyan-500/20" />
          )}

          <Button
            id="mic-toggle"
            size="icon"
            variant="outline"
            onClick={callActive ? stopCall : startCall}
            className={cn(
              "relative z-10 h-20 w-20 rounded-full text-2xl transition-all duration-300",
              "border-2 cursor-pointer",
              callActive
                ? "border-rose-500 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400"
                : "border-cyan-500 bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400",
            )}
          >
            {callActive ? <PhoneOff className="h-8 w-8" /> : <Mic className="h-8 w-8" />}
          </Button>
        </div>

        {/* ---- Status row ---- */}
        <div className="flex items-center gap-3 text-sm">
          {/* connection dot */}
          <span
            className={cn(
              "h-2 w-2 rounded-full",
              isConnected ? "bg-emerald-400" : callActive ? "bg-amber-400 animate-pulse" : "bg-zinc-600",
            )}
          />
          <span className="text-muted-foreground">
            {error
              ? error
              : !callActive
                ? "Ready"
                : isConnected
                  ? "Connected"
                  : "Connecting…"}
          </span>

          {metadata && <SentimentBadge value={metadata.detected_sentiment} />}
        </div>

        {/* ---- Transcript ---- */}
        {transcript && (
          <p className="w-full text-center text-sm text-muted-foreground/80 italic truncate px-4">
            "{transcript}"
          </p>
        )}
      </div>
    </div>
  );
}
