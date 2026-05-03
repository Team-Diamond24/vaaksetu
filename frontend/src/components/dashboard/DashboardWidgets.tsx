import { useEffect, useRef } from "react";
import type { ReasoningOutput, AcousticData, CallState } from "@/types";

/* ------------------------------------------------------------------ */
/*  Transcript entry                                                    */
/* ------------------------------------------------------------------ */
export interface TranscriptEntry {
  id: string;
  sender: "citizen" | "ai";
  text: string;
  timestamp: Date;
}

/* ------------------------------------------------------------------ */
/*  Vulnerability Alert Banner                                          */
/* ------------------------------------------------------------------ */
export function VulnerabilityBanner({
  urgency,
  isHighDistress,
}: {
  urgency: number;
  isHighDistress: boolean;
}) {
  const show = urgency >= 4 || isHighDistress;
  if (!show) return null;

  return (
    <div
      id="vulnerability-banner"
      className="w-full rounded-2xl bg-rose-500/10 border-2 border-rose-500/40 px-6 py-4 flex items-center gap-4 animate-pulse"
    >
      <div className="flex-shrink-0 h-10 w-10 rounded-full bg-rose-500/20 flex items-center justify-center">
        <span className="text-xl">🚨</span>
      </div>
      <div className="flex-1">
        <p className="text-sm font-bold text-rose-300 tracking-wide uppercase">
          Vulnerability Alert
        </p>
        <p className="text-xs text-rose-200/70 mt-0.5">
          {urgency >= 4 && "High urgency level detected. "}
          {isHighDistress && "Acoustic distress markers present. "}
          Immediate supervisor attention required.
        </p>
      </div>
      <div className="flex-shrink-0 flex items-center gap-1">
        {[1, 2, 3].map((i) => (
          <span
            key={i}
            className="h-2 w-2 rounded-full bg-rose-400 animate-ping"
            style={{ animationDelay: `${i * 200}ms` }}
          />
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Call State Breadcrumb                                                */
/* ------------------------------------------------------------------ */
const STATES: { key: CallState; label: string; emoji: string }[] = [
  { key: "LISTENING", label: "Listening", emoji: "🎧" },
  { key: "VERIFYING", label: "Verifying", emoji: "🔍" },
  { key: "CONFIRMED", label: "Confirmed", emoji: "✅" },
];

export function CallStateBreadcrumb({ current }: { current: CallState }) {
  const currentIdx = STATES.findIndex((s) => s.key === current);
  return (
    <div
      id="call-state-breadcrumb"
      className="flex items-center gap-0 w-full select-none"
    >
      {STATES.map((s, i) => {
        const isActive = s.key === current;
        const isDone = i < currentIdx;
        return (
          <div key={s.key} className="flex items-center flex-1 last:flex-none">
            {/* Step circle */}
            <div
              className={`
                flex items-center justify-center h-9 w-9 rounded-full border-2 text-sm font-bold
                transition-all duration-500 flex-shrink-0
                ${isActive
                  ? "border-cyan-400 bg-cyan-500/20 text-cyan-300 shadow-lg shadow-cyan-500/20 scale-110"
                  : isDone
                    ? "border-emerald-500 bg-emerald-500/20 text-emerald-400"
                    : "border-white/10 bg-white/5 text-white/30"
                }
              `}
            >
              {isDone ? "✓" : s.emoji}
            </div>
            <span
              className={`
                ml-2 text-xs font-semibold tracking-wide whitespace-nowrap
                ${isActive
                  ? "text-cyan-300"
                  : isDone
                    ? "text-emerald-400/80"
                    : "text-white/25"
                }
              `}
            >
              {s.label}
            </span>
            {/* Connector line */}
            {i < STATES.length - 1 && (
              <div
                className={`
                  flex-1 h-0.5 mx-3 rounded-full transition-all duration-500
                  ${isDone
                    ? "bg-emerald-500/50"
                    : isActive
                      ? "bg-gradient-to-r from-cyan-500/50 to-white/5"
                      : "bg-white/5"
                  }
                `}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Sentiment Emoji Widget                                              */
/* ------------------------------------------------------------------ */
export function SentimentWidget({ value }: { value: string }) {
  const map: Record<string, { emoji: string; label: string; color: string }> = {
    positive:   { emoji: "😊", label: "Positive",   color: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20" },
    neutral:    { emoji: "😐", label: "Neutral",    color: "text-zinc-400 bg-zinc-500/10 border-zinc-500/20" },
    negative:   { emoji: "😟", label: "Negative",   color: "text-amber-400 bg-amber-500/10 border-amber-500/20" },
    fearful:    { emoji: "😨", label: "Fearful",    color: "text-amber-400 bg-amber-500/10 border-amber-500/20" },
    angry:      { emoji: "😠", label: "Angry",      color: "text-red-400 bg-red-500/10 border-red-500/20" },
    distressed: { emoji: "😰", label: "Distressed", color: "text-orange-400 bg-orange-500/10 border-orange-500/20" },
  };
  const s = map[value] ?? map.neutral;

  return (
    <div
      id="sentiment-widget"
      className={`flex flex-col items-center gap-2 rounded-2xl border p-4 transition-all duration-300 ${s.color}`}
    >
      <span className="text-3xl leading-none">{s.emoji}</span>
      <span className="text-[10px] uppercase tracking-widest font-bold opacity-60">
        Sentiment
      </span>
      <span className="text-xs font-semibold">{s.label}</span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Urgency Heatmap Meter                                               */
/* ------------------------------------------------------------------ */
export function UrgencyMeter({ level }: { level: number }) {
  const segments = [1, 2, 3, 4, 5];
  const colors = [
    "bg-emerald-500",
    "bg-lime-500",
    "bg-amber-500",
    "bg-orange-500",
    "bg-rose-500",
  ];

  return (
    <div
      id="urgency-meter"
      className="flex flex-col gap-2 rounded-2xl border border-white/10 bg-white/5 p-4"
    >
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground/60">
          Urgency
        </span>
        <span
          className={`text-xs font-bold ${
            level >= 4
              ? "text-rose-400"
              : level >= 3
                ? "text-amber-400"
                : "text-emerald-400"
          }`}
        >
          {level}/5
        </span>
      </div>
      <div className="flex gap-1 h-3 w-full">
        {segments.map((seg) => (
          <div
            key={seg}
            className={`
              flex-1 rounded-sm transition-all duration-500
              ${seg <= level
                ? `${colors[seg - 1]} ${seg === level ? "shadow-lg" : ""}`
                : "bg-white/5"
              }
            `}
            style={
              seg <= level
                ? { boxShadow: `0 0 8px ${seg >= 4 ? "rgba(244,63,94,.4)" : "transparent"}` }
                : undefined
            }
          />
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Language & Region Widget                                            */
/* ------------------------------------------------------------------ */
const LANG_NAMES: Record<string, string> = {
  en: "English",
  hi: "Hindi",
  kn: "Kannada",
  ta: "Tamil",
  te: "Telugu",
  mr: "Marathi",
  ur: "Urdu",
};

export function LanguageRegionWidget({
  languageCode,
  reasoning,
}: {
  languageCode: string;
  reasoning: ReasoningOutput | null;
}) {
  const langName = LANG_NAMES[languageCode] ?? languageCode.toUpperCase();
  const intent = reasoning?.intent ?? "—";

  return (
    <div
      id="language-region-widget"
      className="flex flex-col gap-2 rounded-2xl border border-white/10 bg-white/5 p-4"
    >
      <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground/60">
        Language & Intent
      </span>
      <div className="flex items-center gap-2">
        <span className="text-lg">🌐</span>
        <span className="text-sm font-semibold text-white/90">{langName}</span>
        <span className="text-[10px] font-mono text-muted-foreground bg-white/5 px-1.5 py-0.5 rounded">
          {languageCode}
        </span>
      </div>
      <div className="flex items-center gap-2 mt-1">
        <span className="text-lg">
          {intent === "Medical" ? "🏥" : intent === "Fire" ? "🔥" : intent === "Crime" ? "🚔" : "📋"}
        </span>
        <span className="text-sm font-medium text-white/70">{intent}</span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Acoustic Monitor Widget                                             */
/* ------------------------------------------------------------------ */
export function AcousticWidget({ data }: { data: AcousticData | null }) {
  if (!data) {
    return (
      <div className="flex flex-col gap-2 rounded-2xl border border-white/10 bg-white/5 p-4">
        <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground/60">
          Acoustic Analysis
        </span>
        <span className="text-xs text-muted-foreground">Waiting for audio…</span>
      </div>
    );
  }

  const envConfig = {
    quiet:    { emoji: "🏠", label: "Quiet",   color: "text-emerald-400" },
    moderate: { emoji: "👥", label: "Moderate", color: "text-amber-400" },
    noisy:    { emoji: "🚗", label: "Noisy",    color: "text-orange-400" },
    chaotic:  { emoji: "🚨", label: "Chaotic",  color: "text-rose-400" },
  };
  const env = envConfig[data.environment] ?? envConfig.quiet;

  const loudnessConfig = {
    whisper:  { label: "Whisper",  bars: 1 },
    normal:   { label: "Normal",   bars: 2 },
    loud:     { label: "Loud",     bars: 3 },
    shouting: { label: "Shouting", bars: 4 },
  };
  const loud = loudnessConfig[data.loudness] ?? loudnessConfig.normal;

  return (
    <div
      id="acoustic-widget"
      className={`flex flex-col gap-3 rounded-2xl border p-4 transition-all duration-300 ${
        data.is_high_distress
          ? "border-rose-500/40 bg-rose-500/5"
          : "border-white/10 bg-white/5"
      }`}
    >
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground/60">
          Acoustic Analysis
        </span>
        {data.is_high_distress && (
          <span className="text-[10px] font-bold text-rose-400 animate-pulse">
            ⚠ HIGH DISTRESS
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        {/* Environment */}
        <div className="flex items-center gap-2">
          <span className={`text-lg ${env.color}`}>{env.emoji}</span>
          <div>
            <p className="text-[10px] text-muted-foreground/60 uppercase">Env</p>
            <p className={`text-xs font-semibold ${env.color}`}>{env.label}</p>
          </div>
        </div>

        {/* Loudness */}
        <div className="flex items-center gap-2">
          <div className="flex items-end gap-0.5 h-4">
            {[1, 2, 3, 4].map((b) => (
              <div
                key={b}
                className={`w-1 rounded-t-sm transition-all ${
                  b <= loud.bars ? "bg-cyan-400" : "bg-white/10"
                }`}
                style={{ height: `${b * 25}%` }}
              />
            ))}
          </div>
          <div>
            <p className="text-[10px] text-muted-foreground/60 uppercase">Volume</p>
            <p className="text-xs font-semibold text-white/80">{loud.label}</p>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Live Transcript Feed                                                */
/* ------------------------------------------------------------------ */
export function TranscriptFeed({
  entries,
}: {
  entries: TranscriptEntry[];
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries.length]);

  return (
    <div
      id="transcript-feed"
      className="flex flex-col gap-3 h-full overflow-y-auto pr-2 custom-scrollbar"
    >
      {entries.length === 0 && (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-sm text-muted-foreground/40 italic">
            Call transcript will appear here…
          </p>
        </div>
      )}

      {entries.map((entry) => (
        <div
          key={entry.id}
          className={`flex ${entry.sender === "citizen" ? "justify-start" : "justify-end"}`}
        >
          <div
            className={`
              max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed
              ${entry.sender === "citizen"
                ? "bg-cyan-500/10 border border-cyan-500/20 text-cyan-100 rounded-bl-md"
                : "bg-violet-500/10 border border-violet-500/20 text-violet-100 rounded-br-md"
              }
            `}
          >
            <div className="flex items-center gap-2 mb-1.5">
              <span className="text-[10px] font-bold uppercase tracking-wider opacity-60">
                {entry.sender === "citizen" ? "👤 Citizen" : "🤖 VaakSetu AI"}
              </span>
              <span className="text-[9px] text-muted-foreground/40 font-mono">
                {entry.timestamp.toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                })}
              </span>
            </div>
            <p>{entry.text}</p>
          </div>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
