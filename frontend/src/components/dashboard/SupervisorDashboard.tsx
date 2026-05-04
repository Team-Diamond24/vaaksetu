import { useCallback, useEffect, useRef, useState } from "react";
import { ClipboardList, Mic, PhoneOff, Radio, Waves } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { useVoiceClient } from "@/hooks/use-voice-client";
import { AudioVisualizer } from "@/components/voice-client/AudioVisualizer";
import { cn } from "@/lib/utils";
import { ComplaintsTable } from "./ComplaintsTable";
import {
  AcousticWidget,
  CallStateBreadcrumb,
  LanguageRegionWidget,
  SentimentWidget,
  TranscriptFeed,
  type TranscriptEntry,
  UrgencyMeter,
  VulnerabilityBanner,
} from "./DashboardWidgets";

type DashboardView = "live" | "records";

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

  const [view, setView] = useState<DashboardView>("live");
  const [entries, setEntries] = useState<TranscriptEntry[]>([]);
  const [showSummaryModal, setShowSummaryModal] = useState(false);
  const lastTranscriptRef = useRef("");
  const lastAiMessageRef = useRef("");

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

  const prevAiMessage = useRef(reasoning?.response_text ?? reasoning?.restatement);
  const currentAiMessage = reasoning?.response_text ?? reasoning?.restatement ?? null;
  if (currentAiMessage && currentAiMessage !== prevAiMessage.current) {
    prevAiMessage.current = currentAiMessage;
    if (currentAiMessage !== lastAiMessageRef.current) {
      lastAiMessageRef.current = currentAiMessage;
      setEntries((prev) => [
        ...prev,
        {
          id: `ai-${Date.now()}`,
          sender: "ai",
          text: currentAiMessage,
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
      lastAiMessageRef.current = "";
    } else {
      setShowSummaryModal(false);
      setView("live");
      await startCall();
    }
  }, [callActive, startCall, stopCall]);

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

  const ScoreRing = ({
    value,
    label,
    ringColor,
  }: {
    value: number;
    label: string;
    ringColor: string;
  }) => {
    const pct = Math.min(100, Math.max(0, value * 10));
    return (
      <div className="flex flex-col items-center gap-2">
        <div
          className="relative h-24 w-24 rounded-full grid place-items-center"
          style={{
            background: `conic-gradient(${ringColor} ${pct}%, rgba(255,255,255,0.08) ${pct}% 100%)`,
          }}
        >
          <div className="h-16 w-16 rounded-full bg-white border border-black/10 grid place-items-center text-lg font-bold text-black">
            {value}
          </div>
        </div>
        <span className="text-xs text-black/60">{label}</span>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-white text-black">
      <header className="sticky top-0 z-50 backdrop-blur-xl bg-white/90 border-b border-black/10">
        <div className="max-w-[1600px] mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-black/5 border border-black/10 flex items-center justify-center">
              <Radio className="h-4 w-4 text-black" />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight">
                VaakSetu <span className="text-black/60 font-normal">Command Center</span>
              </h1>
              <p className="text-[10px] text-black/50 uppercase tracking-widest">
                1092 Helpline • Supervisor Dashboard
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 rounded-xl border border-black/10 bg-white p-1">
              <Button
                variant="ghost"
                className={cn(
                  "h-9 gap-2 cursor-pointer rounded-lg",
                  view === "live" && "bg-black text-white",
                )}
                onClick={() => setView("live")}
              >
                <Waves className="h-4 w-4" />
                Live Call View
              </Button>
              <Button
                variant="ghost"
                className={cn(
                  "h-9 gap-2 cursor-pointer rounded-lg",
                  view === "records" && "bg-black text-white",
                )}
                onClick={() => setView("records")}
              >
                <ClipboardList className="h-4 w-4" />
                Records Dashboard
              </Button>
            </div>

            <div className="flex items-center gap-2">
              <span
                className={cn(
                  "h-2 w-2 rounded-full",
                  isConnected
                    ? "bg-black"
                    : callActive
                      ? "bg-black/70 animate-pulse"
                      : "bg-black/30",
                )}
              />
              <span className="text-xs text-black/60">
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
                        : "Connecting..."}
              </span>
            </div>

            {callActive && isAiMuted && (
              <span className="text-[11px] font-bold uppercase tracking-wider text-black bg-black/5 border border-black/20 px-3 py-1 rounded-full">
                Human in Control
              </span>
            )}

            <Button
              id="call-toggle"
              onClick={handleToggleCall}
              className={cn(
                "gap-2 rounded-xl px-5 cursor-pointer",
                callActive
                  ? "bg-black text-white border border-black"
                  : "bg-white text-black border border-black/20",
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

      <main className="max-w-[1600px] mx-auto px-6 py-6 flex flex-col gap-6">
        {view === "live" ? (
          <>
            <VulnerabilityBanner urgency={urgency} isHighDistress={isHighDistress} />

            {callActive && (
              <Card className="border-black/10 bg-white">
                <CardContent className="p-4">
                  <CallStateBreadcrumb current={callState} />
                </CardContent>
              </Card>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-8 flex flex-col gap-6">
                <Card className="flex-1 border-black/10 bg-white overflow-hidden">
                  <CardContent className="p-0 flex flex-col h-[600px]">
                    <div className="px-6 py-4 border-b border-black/10 flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div
                          className={cn(
                            "h-3 w-3 rounded-full",
                            callActive ? "bg-black animate-pulse" : "bg-black/30",
                          )}
                        />
                        <span className="text-sm font-semibold">Live Call Feed</span>
                        {callActive && (
                          <span className="text-[10px] text-black font-mono bg-black/5 px-2 py-0.5 rounded-full">
                            ● REC
                          </span>
                        )}
                      </div>
                      {metadata?.session_id && (
                        <span className="text-[10px] font-mono text-black/40">
                          Session: {metadata.session_id.slice(0, 8)}...
                        </span>
                      )}
                    </div>

                    <div className="px-6 py-3 border-b border-black/10 bg-white">
                      <AudioVisualizer analyser={analyserNode.current} isActive={isRecording} />
                    </div>

                    <div className="flex-1 px-6 py-4 overflow-hidden">
                      <TranscriptFeed entries={entries} />
                    </div>
                  </CardContent>
                </Card>
              </div>

              <div className="lg:col-span-4 flex flex-col gap-4">
                <SentimentWidget value={sentiment} />
                <UrgencyMeter level={urgency} />
                <LanguageRegionWidget languageCode={langCode} reasoning={reasoning} />
                <Separator className="bg-black/10" />
                <AcousticWidget data={acousticData} />

                {reasoning?.restatement && (
                  <Card className="border-black/10 bg-white">
                    <CardContent className="p-4">
                      <p className="text-[10px] uppercase tracking-widest font-bold text-black/50 mb-2">
                        AI Restatement
                      </p>
                      <p className="text-sm text-black leading-relaxed">
                        {reasoning.restatement}
                      </p>
                      {reasoning.needs_verification && (
                        <div className="mt-3 flex items-center gap-2 text-black/70">
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
          </>
        ) : (
          <ComplaintsTable />
        )}
      </main>

      {shouldShowSummary && callSummary && (
        <div className="fixed inset-0 z-[60] bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
          <Card className="w-full max-w-2xl border-black/10 bg-white shadow-2xl">
            <CardContent className="p-6 space-y-5">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-bold">Call Summary</h2>
                  <p className="text-xs text-black/50">Post-call performance report</p>
                </div>
                <Button
                  variant="ghost"
                  onClick={() => setShowSummaryModal(false)}
                  className="cursor-pointer"
                >
                  Close
                </Button>
              </div>

              <div className="grid grid-cols-2 gap-6">
                <ScoreRing value={callSummary.understanding_score} label="Understanding Score" ringColor="#111111" />
                <ScoreRing value={callSummary.cultural_accuracy} label="Cultural Accuracy" ringColor="#111111" />
              </div>

              <div className="rounded-xl border border-black/10 bg-black/5 p-4">
                <p className="text-[10px] uppercase tracking-widest text-black/60 mb-1">
                  Bottleneck Detected
                </p>
                <p className="text-sm text-black">{callSummary.bottleneck_detected}</p>
              </div>

              <div className="rounded-xl border border-black/10 bg-black/5 p-4">
                <p className="text-[10px] uppercase tracking-widest text-black/60 mb-1">
                  Coaching Tip
                </p>
                <p className="text-sm text-black">{callSummary.coaching_tip}</p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
