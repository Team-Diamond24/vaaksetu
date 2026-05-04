import {
  AlertTriangle,
  Car,
  CheckCircle2,
  Home,
  Mic,
  MicOff,
  PhoneOff,
  ShieldCheck,
  Siren,
  Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useVoiceClient } from "@/hooks/use-voice-client";
import { AudioVisualizer } from "./AudioVisualizer";
import { cn } from "@/lib/utils";
import type { AcousticData, CallState } from "@/types";

function SentimentBadge({ value }: { value: string }) {
  const map: Record<string, { bg: string; label: string }> = {
    positive: { bg: "bg-emerald-500/20 text-emerald-400", label: "Positive" },
    negative: { bg: "bg-rose-500/20 text-rose-400", label: "Negative" },
    neutral: { bg: "bg-zinc-500/20 text-zinc-400", label: "Neutral" },
    fearful: { bg: "bg-amber-500/20 text-amber-400", label: "Fearful" },
    angry: { bg: "bg-red-500/20 text-red-400", label: "Angry" },
    distressed: { bg: "bg-orange-500/20 text-orange-400", label: "Distressed" },
  };
  const s = map[value] ?? map.neutral;
  return (
    <span className={cn("px-3 py-1 rounded-full text-xs font-medium", s.bg)}>
      {s.label}
    </span>
  );
}

function StateBadge({ state }: { state: CallState }) {
  const config: Record<CallState, { bg: string; icon: React.ReactNode; label: string }> = {
    GREETING: {
      bg: "bg-sky-500/15 border-sky-500/30 text-sky-400",
      icon: <Mic className="h-3 w-3" />,
      label: "Greeting",
    },
    LISTENING: {
      bg: "bg-cyan-500/15 border-cyan-500/30 text-cyan-400",
      icon: <Mic className="h-3 w-3" />,
      label: "Listening",
    },
    VERIFYING: {
      bg: "bg-amber-500/15 border-amber-500/30 text-amber-400",
      icon: <ShieldCheck className="h-3 w-3" />,
      label: "Awaiting Confirmation",
    },
    ASSURANCE: {
      bg: "bg-emerald-500/15 border-emerald-500/30 text-emerald-400",
      icon: <CheckCircle2 className="h-3 w-3" />,
      label: "Assurance",
    },
    ESCALATED: {
      bg: "bg-rose-500/15 border-rose-500/30 text-rose-400",
      icon: <AlertTriangle className="h-3 w-3" />,
      label: "Escalated",
    },
  };
  const c = config[state];
  return (
    <span className={cn("flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border", c.bg)}>
      {c.icon}
      {c.label}
    </span>
  );
}

function DistressMonitor({ data }: { data: AcousticData | null }) {
  if (!data) return null;

  const getLevelColor = (level: number) => {
    if (level <= 2) return "bg-emerald-500";
    if (level <= 3) return "bg-amber-500";
    return "bg-rose-500";
  };

  return (
    <div className="flex flex-col gap-2 w-full max-w-[200px]">
      <div className="flex items-center justify-between text-[10px] uppercase tracking-wider font-bold text-muted-foreground/60">
        <span>Stress Monitor</span>
        <span className={cn(data.is_high_distress && "text-rose-400 animate-pulse")}>
          {data.is_high_distress ? "HIGH DISTRESS" : "NORMAL"}
        </span>
      </div>
      <div className="flex gap-1 h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
        {[1, 2, 3, 4, 5].map((i) => (
          <div
            key={i}
            className={cn(
              "flex-1 transition-all duration-300",
              i <= data.distress_level ? getLevelColor(data.distress_level) : "bg-white/5",
            )}
          />
        ))}
      </div>
    </div>
  );
}

function EnvironmentIndicator({ env }: { env: AcousticData["environment"] }) {
  const config = {
    quiet: { icon: <Home className="h-4 w-4" />, label: "Quiet Room", color: "text-emerald-400" },
    moderate: { icon: <Users className="h-4 w-4" />, label: "Moderate Ambient", color: "text-amber-400" },
    noisy: { icon: <Car className="h-4 w-4" />, label: "Noisy/Traffic", color: "text-orange-400" },
    chaotic: { icon: <Siren className="h-4 w-4" />, label: "Chaotic/Emergency", color: "text-rose-400 animate-pulse" },
  };
  const c = config[env] || config.quiet;

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-white/5 border border-white/10">
      <span className={c.color}>{c.icon}</span>
      <span className="text-[11px] font-medium text-muted-foreground">{c.label}</span>
    </div>
  );
}

export function VoiceClient() {
  const {
    isConnected,
    isRecording,
    callActive,
    isAiSpeaking,
    isAiMuted,
    isThinking,
    callState,
    error,
    metadata,
    transcript,
    reasoning,
    acousticData,
    startCall,
    stopCall,
    toggleTakeover,
    analyserNode,
  } = useVoiceClient();

  return (
    <div className="w-full max-w-lg mx-auto select-none">
      <div
        className={cn(
          "relative rounded-3xl border border-white/10 p-8",
          "bg-white/5 backdrop-blur-xl shadow-2xl",
          "flex flex-col items-center gap-6 transition-all duration-500",
          callActive && "ring-1 ring-cyan-500/30 shadow-cyan-500/10",
          callState === "VERIFYING" && "ring-1 ring-amber-500/30 shadow-amber-500/10",
          callState === "ASSURANCE" && "ring-1 ring-emerald-500/30 shadow-emerald-500/10",
          acousticData?.is_high_distress && "ring-2 ring-rose-500/50 shadow-rose-500/20 bg-rose-500/5",
        )}
      >
        {callActive && (
          <div className="w-full flex items-center justify-between gap-4 px-2">
            <DistressMonitor data={acousticData} />
            {acousticData && <EnvironmentIndicator env={acousticData.environment} />}
          </div>
        )}

        <AudioVisualizer analyser={analyserNode.current} isActive={isRecording} />

        <div className="relative flex items-center justify-center">
          {isRecording && (
            <span
              className={cn(
                "absolute inset-0 rounded-full animate-[voicePulse_2s_ease-in-out_infinite]",
                acousticData?.is_high_distress ? "bg-rose-500/30" : "bg-cyan-500/20",
              )}
            />
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

        {callActive && (
          <Button
            id="takeover-toggle"
            onClick={toggleTakeover}
            className={cn(
              "w-full h-12 rounded-xl text-sm font-bold tracking-wide border-2 cursor-pointer",
              isAiMuted
                ? "bg-rose-600/20 hover:bg-rose-600/30 text-rose-300 border-rose-500/60"
                : "bg-amber-500/15 hover:bg-amber-500/25 text-amber-200 border-amber-400/60",
            )}
            variant="ghost"
          >
            {isAiMuted ? (
              <>
                <Mic className="h-4 w-4 mr-2" />
                RELEASE TO AI
              </>
            ) : (
              <>
                <MicOff className="h-4 w-4 mr-2" />
                TAKE OVER CALL
              </>
            )}
          </Button>
        )}

        <div className="flex items-center gap-3 text-sm flex-wrap justify-center">
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
                : isAiSpeaking
                  ? "AI Speaking..."
                  : isConnected
                    ? isThinking
                      ? "Thinking..."
                      : "Connected"
                    : "Connecting..."}
          </span>

          {metadata && <SentimentBadge value={metadata.detected_sentiment} />}

          {isAiSpeaking && (
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-violet-400 animate-pulse" />
              <span className="text-xs text-violet-400 font-medium">TTS</span>
            </span>
          )}
          {isAiMuted && (
            <span className="flex items-center gap-1.5 text-rose-300">
              <span className="h-2 w-2 rounded-full bg-rose-400 animate-pulse" />
              <span className="text-xs font-semibold tracking-wide">Human in Control</span>
            </span>
          )}
        </div>

        {callActive && (
          <div className="flex items-center gap-2">
            <StateBadge state={callState} />
          </div>
        )}

        {callState === "VERIFYING" && (
          <div className="w-full rounded-xl bg-amber-500/10 border border-amber-500/20 px-4 py-3 text-center animate-pulse">
            <p className="text-xs text-amber-400/70 font-medium mb-1">Waiting for your confirmation...</p>
            <p className="text-sm text-amber-200">Please say <strong>Yes</strong> or <strong>No</strong> to confirm.</p>
          </div>
        )}

        {callState === "ASSURANCE" && (
          <div className="w-full rounded-xl bg-emerald-500/10 border border-emerald-500/20 px-4 py-3 text-center">
            <p className="text-xs text-emerald-400/70 font-medium mb-1">Assurance</p>
            <p className="text-sm text-emerald-200">Your report has been confirmed. Help is on the way.</p>
          </div>
        )}

        {transcript && (
          <p className="w-full text-center text-sm text-muted-foreground/80 italic truncate px-4">
            "{transcript}"
          </p>
        )}

        {reasoning?.restatement && (
          <div className="w-full rounded-xl bg-violet-500/10 border border-violet-500/20 px-4 py-3 text-center">
            <p className="text-xs text-violet-400/70 font-medium mb-1">AI Response</p>
            <p className="text-sm text-violet-200">{reasoning.restatement}</p>
          </div>
        )}
      </div>
    </div>
  );
}
