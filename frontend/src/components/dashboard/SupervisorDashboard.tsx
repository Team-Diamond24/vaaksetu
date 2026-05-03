import { useCallback, useEffect, useRef, useState } from "react";
import { Mic, PhoneOff, Radio } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { useVoiceClient } from "@/hooks/use-voice-client";
import { AudioVisualizer } from "@/components/voice-client/AudioVisualizer";
import { cn } from "@/lib/utils";

import {
  VulnerabilityBanner,
  CallStateBreadcrumb,
  SentimentWidget,
  UrgencyMeter,
  LanguageRegionWidget,
  AcousticWidget,
  TranscriptFeed,
  type TranscriptEntry,
} from "./DashboardWidgets";

/* ------------------------------------------------------------------ */
/*  Supervisor Dashboard                                                */
/* ------------------------------------------------------------------ */
export function SupervisorDashboard() {
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
    callSummary,
    startCall,
    stopCall,
    analyserNode,
  } = useVoiceClient();

  /* ---- Transcript history ---- */
  const [entries, setEntries] = useState<TranscriptEntry[]>([]);
  const [showSummaryModal, setShowSummaryModal] = useState(false);
  const lastTranscriptRef = useRef("");
  const lastRestatementRef = useRef("");

  /* Append citizen transcript when it changes */
  const prevTranscript = useRef(transcript);
  if (transcript && transcript !== prevTranscript.current) {
    prevTranscript.current = transcript;
    if (transcript !== lastTranscriptRef.current) {
      lastTranscriptRef.current = transcript;
      setEntries((prev) => [
        ...prev,
        {
          id: `citizen-${Date.now()}`,
          sender: "citizen",
          text: transcript,
          timestamp: new Date(),
        },
      ]);
    }
  }

  /* Append AI restatement when it changes */
  const prevRestatement = useRef(reasoning?.restatement);
  if (
    reasoning?.restatement &&
    reasoning.restatement !== prevRestatement.current
  ) {
    prevRestatement.current = reasoning.restatement;
    if (reasoning.restatement !== lastRestatementRef.current) {
      lastRestatementRef.current = reasoning.restatement;
      setEntries((prev) => [
        ...prev,
        {
          id: `ai-${Date.now()}`,
          sender: "ai",
          text: reasoning.restatement,
          timestamp: new Date(),
        },
      ]);
    }
  }

  const handleToggleCall = useCallback(async () => {
    if (callActive) {
      stopCall();
      setEntries([]);
      lastTranscriptRef.current = "";
      lastRestatementRef.current = "";
    } else {
      setShowSummaryModal(false);
      await startCall();
    }
  }, [callActive, startCall, stopCall]);

  /* ---- Derived values ---- */
  const urgency = reasoning?.urgency_level ?? 0;
  const sentiment = reasoning?.sentiment ?? metadata?.detected_sentiment ?? "neutral";
  const langCode = reasoning?.language_code ?? "—";
  const isHighDistress = acousticData?.is_high_distress ?? false;
  const shouldShowSummary = !callActive && !!callSummary && showSummaryModal;

  useEffect(() => {
    if (!callActive && callSummary) {
      setShowSummaryModal(true);
    }
  }, [callActive, callSummary]);

  const ScoreRing = ({ value, label, ringColor }: { value: number; label: string; ringColor: string }) => {
    const pct = Math.min(100, Math.max(0, value * 10));
    return (
      <div className="flex flex-col items-center gap-2">
        <div
          className="relative h-24 w-24 rounded-full grid place-items-center"
          style={{
            background: `conic-gradient(${ringColor} ${pct}%, rgba(255,255,255,0.08) ${pct}% 100%)`,
          }}
        >
          <div className="h-16 w-16 rounded-full bg-zinc-950/90 border border-white/10 grid place-items-center text-lg font-bold text-white">
            {value}
          </div>
        </div>
        <span className="text-xs text-muted-foreground">{label}</span>
      </div>
    );
  };

  return (
    <div className="dark min-h-screen bg-background text-foreground">
      {/* ── Top bar ────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-50 backdrop-blur-xl bg-background/80 border-b border-white/5">
        <div className="max-w-[1600px] mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center">
              <Radio className="h-4 w-4 text-cyan-400" />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight">
                VaakSetu <span className="text-muted-foreground font-normal">Command Center</span>
              </h1>
              <p className="text-[10px] text-muted-foreground/60 uppercase tracking-widest">
                1092 Helpline • Supervisor Dashboard
              </p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            {/* Connection status */}
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  "h-2 w-2 rounded-full",
                  isConnected
                    ? "bg-emerald-400"
                    : callActive
                      ? "bg-amber-400 animate-pulse"
                      : "bg-zinc-600"
                )}
              />
              <span className="text-xs text-muted-foreground">
                {error
                  ? error
                  : !callActive
                    ? "Standby"
                    : isAiSpeaking
                      ? "AI Speaking"
                      : isConnected
                        ? isThinking
                          ? "Thinking..."
                          : "Live"
                        : "Connecting…"}
              </span>
            </div>

            {callActive && isAiMuted && (
              <span className="text-[11px] font-bold uppercase tracking-wider text-rose-300 bg-rose-500/15 border border-rose-500/30 px-3 py-1 rounded-full">
                Human in Control
              </span>
            )}

            {/* Call toggle */}
            <Button
              id="call-toggle"
              onClick={handleToggleCall}
              className={cn(
                "gap-2 rounded-xl px-5 cursor-pointer",
                callActive
                  ? "bg-rose-500/20 hover:bg-rose-500/30 text-rose-400 border border-rose-500/30"
                  : "bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-400 border border-cyan-500/30"
              )}
              variant="ghost"
            >
              {callActive ? (
                <>
                  <PhoneOff className="h-4 w-4" /> End Call
                </>
              ) : (
                <>
                  <Mic className="h-4 w-4" /> Start Call
                </>
              )}
            </Button>
          </div>
        </div>
      </header>

      {/* ── Main grid ──────────────────────────────────────────────── */}
      <main className="max-w-[1600px] mx-auto px-6 py-6 flex flex-col gap-6">
        {/* Vulnerability banner */}
        <VulnerabilityBanner urgency={urgency} isHighDistress={isHighDistress} />

        {/* Call state breadcrumb */}
        {callActive && (
          <Card className="border-white/10 bg-white/[0.02]">
            <CardContent className="p-4">
              <CallStateBreadcrumb current={callState} />
            </CardContent>
          </Card>
        )}

        {/* ── 3-column grid ──────────────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* ── LEFT COLUMN: Live Call (8 cols) ──────────────────── */}
          <div className="lg:col-span-8 flex flex-col gap-6">
            {/* Live call card */}
            <Card className="flex-1 border-white/10 bg-white/[0.02] overflow-hidden">
              <CardContent className="p-0 flex flex-col h-[600px]">
                {/* Card header */}
                <div className="px-6 py-4 border-b border-white/5 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div
                      className={cn(
                        "h-3 w-3 rounded-full",
                        callActive ? "bg-rose-500 animate-pulse" : "bg-zinc-600"
                      )}
                    />
                    <span className="text-sm font-semibold">Live Call Feed</span>
                    {callActive && (
                      <span className="text-[10px] text-rose-400 font-mono bg-rose-500/10 px-2 py-0.5 rounded-full">
                        ● REC
                      </span>
                    )}
                  </div>
                  {metadata?.session_id && (
                    <span className="text-[10px] font-mono text-muted-foreground/40">
                      Session: {metadata.session_id.slice(0, 8)}…
                    </span>
                  )}
                </div>

                {/* Visualizer strip */}
                <div className="px-6 py-3 border-b border-white/5 bg-white/[0.01]">
                  <AudioVisualizer
                    analyser={analyserNode.current}
                    isActive={isRecording}
                  />
                </div>

                {/* Transcript feed */}
                <div className="flex-1 px-6 py-4 overflow-hidden">
                  <TranscriptFeed entries={entries} />
                </div>
              </CardContent>
            </Card>
          </div>

          {/* ── RIGHT COLUMN: Widgets (4 cols) ──────────────────── */}
          <div className="lg:col-span-4 flex flex-col gap-4">
            {/* Sentiment */}
            <SentimentWidget value={sentiment} />

            {/* Urgency meter */}
            <UrgencyMeter level={urgency} />

            {/* Language & Region */}
            <LanguageRegionWidget
              languageCode={langCode}
              reasoning={reasoning}
            />

            <Separator className="bg-white/5" />

            {/* Acoustic analysis */}
            <AcousticWidget data={acousticData} />

            {/* AI Restatement card */}
            {reasoning?.restatement && (
              <Card className="border-violet-500/20 bg-violet-500/5">
                <CardContent className="p-4">
                  <p className="text-[10px] uppercase tracking-widest font-bold text-violet-400/60 mb-2">
                    AI Restatement
                  </p>
                  <p className="text-sm text-violet-200 leading-relaxed">
                    {reasoning.restatement}
                  </p>
                  {reasoning.needs_verification && (
                    <div className="mt-3 flex items-center gap-2 text-amber-400">
                      <span className="text-xs">⚠</span>
                      <span className="text-[10px] font-bold uppercase tracking-wider">
                        Needs Verification
                      </span>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </main>

      {shouldShowSummary && callSummary && (
        <div className="fixed inset-0 z-[60] bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <Card className="w-full max-w-2xl border-white/15 bg-zinc-950/95 shadow-2xl">
            <CardContent className="p-6 space-y-5">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-bold">Call Summary</h2>
                  <p className="text-xs text-muted-foreground">Post-call performance report</p>
                </div>
                <Button variant="ghost" onClick={() => setShowSummaryModal(false)} className="cursor-pointer">
                  Close
                </Button>
              </div>

              <div className="grid grid-cols-2 gap-6">
                <ScoreRing value={callSummary.understanding_score} label="Understanding Score" ringColor="#22d3ee" />
                <ScoreRing value={callSummary.cultural_accuracy} label="Cultural Accuracy" ringColor="#34d399" />
              </div>

              <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-4">
                <p className="text-[10px] uppercase tracking-widest text-amber-300/80 mb-1">Bottleneck Detected</p>
                <p className="text-sm text-amber-100">{callSummary.bottleneck_detected}</p>
              </div>

              <div className="rounded-xl border border-violet-500/20 bg-violet-500/10 p-4">
                <p className="text-[10px] uppercase tracking-widest text-violet-300/80 mb-1">Coaching Tip</p>
                <p className="text-sm text-violet-100">{callSummary.coaching_tip}</p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
