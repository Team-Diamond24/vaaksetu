import { useEffect, useRef } from "react";
import type { AcousticData, CallState, ReasoningOutput } from "@/types";

export interface TranscriptEntry {
  id: string;
  sender: "citizen" | "ai";
  text: string;
  timestamp: Date;
}

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
      className="w-full rounded-2xl bg-black/5 border border-black/20 px-6 py-4 flex items-center gap-4"
    >
      <div className="flex-shrink-0 h-10 w-10 rounded-full bg-black/10 flex items-center justify-center">
        <span className="text-xl">🚨</span>
      </div>
      <div className="flex-1">
        <p className="text-sm font-bold text-black tracking-wide uppercase">
          Vulnerability Alert
        </p>
        <p className="text-xs text-black/60 mt-0.5">
          {urgency >= 4 && "High urgency level detected. "}
          {isHighDistress && "Acoustic distress markers present. "}
          Immediate supervisor attention required.
        </p>
      </div>
      <div className="flex-shrink-0 flex items-center gap-1">
        {[1, 2, 3].map((i) => (
          <span
            key={i}
            className="h-2 w-2 rounded-full bg-black/40"
            style={{ animationDelay: `${i * 200}ms` }}
          />
        ))}
      </div>
    </div>
  );
}

const STATES: { key: CallState; label: string; emoji: string }[] = [
  { key: "GREETING", label: "Greeting", emoji: "👋" },
  { key: "LISTENING", label: "Listening", emoji: "🎧" },
  { key: "WAITING_FOR_LOCATION", label: "Location", emoji: "📍" },
  { key: "VERIFYING", label: "Verifying", emoji: "🔍" },
  { key: "ASSURANCE", label: "Assurance", emoji: "✅" },
  { key: "ESCALATED", label: "Escalated", emoji: "🚨" },
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
            <div
              className={`
                flex items-center justify-center h-9 w-9 rounded-full border-2 text-sm font-bold
                transition-all duration-500 flex-shrink-0
                ${isActive
                  ? "border-black bg-black text-white scale-110"
                  : isDone
                    ? "border-black bg-black/10 text-black"
                    : "border-black/10 bg-white text-black/40"
                }
              `}
            >
              {isDone ? "✓" : s.emoji}
            </div>
            <span
              className={`
                ml-2 text-xs font-semibold tracking-wide whitespace-nowrap
                ${isActive
                  ? "text-black"
                  : isDone
                    ? "text-black/70"
                    : "text-black/40"
                }
              `}
            >
              {s.label}
            </span>
            {i < STATES.length - 1 && (
              <div
                className={`
                  flex-1 h-0.5 mx-3 rounded-full transition-all duration-500
                  ${isDone
                    ? "bg-black/40"
                    : isActive
                      ? "bg-black/60"
                      : "bg-black/10"
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

export function SentimentWidget({ value }: { value: string }) {
  const map: Record<string, { emoji: string; label: string; color: string }> = {
    positive: { emoji: "😊", label: "Positive", color: "text-black bg-white border-black/10" },
    neutral: { emoji: "😐", label: "Neutral", color: "text-black/70 bg-white border-black/10" },
    negative: { emoji: "😟", label: "Negative", color: "text-black bg-white border-black/10" },
    fearful: { emoji: "😨", label: "Fearful", color: "text-black bg-white border-black/10" },
    angry: { emoji: "😠", label: "Angry", color: "text-black bg-white border-black/10" },
    distressed: { emoji: "😰", label: "Distressed", color: "text-black bg-white border-black/10" },
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
      className="flex flex-col gap-2 rounded-2xl border border-black/10 bg-white p-4"
    >
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-widest font-bold text-black/50">
          Urgency
        </span>
        <span
          className={`text-xs font-bold ${
            level >= 4
              ? "text-black"
              : level >= 3
                ? "text-black/80"
                : "text-black/60"
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
                ? `bg-black ${seg === level ? "shadow-lg" : ""}`
                : "bg-black/5"
              }
            `}
            style={
              seg <= level
                ? { boxShadow: `0 0 8px rgba(0,0,0,0.25)` }
                : undefined
            }
          />
        ))}
      </div>
    </div>
  );
}

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
      className="flex flex-col gap-2 rounded-2xl border border-black/10 bg-white p-4"
    >
      <span className="text-[10px] uppercase tracking-widest font-bold text-black/50">
        Language & Intent
      </span>
      <div className="flex items-center gap-2">
        <span className="text-lg">🌐</span>
        <span className="text-sm font-semibold text-black">{langName}</span>
        <span className="text-[10px] font-mono text-black/60 bg-black/5 px-1.5 py-0.5 rounded">
          {languageCode}
        </span>
      </div>
      <div className="flex items-center gap-2 mt-1">
        <span className="text-lg">
          {intent === "Medical" ? "🏥" : intent === "Fire" ? "🔥" : intent === "Crime" ? "🚔" : "📋"}
        </span>
        <span className="text-sm font-medium text-black/70">{intent}</span>
      </div>
      {reasoning?.location && (
        <div className="flex items-center gap-2 mt-1">
          <span className="text-lg">📍</span>
          <span className="text-sm font-medium text-black/70">{reasoning.location}</span>
        </div>
      )}
    </div>
  );
}

export function AcousticWidget({ data }: { data: AcousticData | null }) {
  if (!data) {
    return (
      <div className="flex flex-col gap-2 rounded-2xl border border-black/10 bg-white p-4">
        <span className="text-[10px] uppercase tracking-widest font-bold text-black/50">
          Acoustic Analysis
        </span>
        <span className="text-xs text-black/50">Waiting for audio...</span>
      </div>
    );
  }

  const envConfig = {
    quiet: { emoji: "🏠", label: "Quiet", color: "text-black" },
    moderate: { emoji: "👥", label: "Moderate", color: "text-black" },
    noisy: { emoji: "🚗", label: "Noisy", color: "text-black" },
    chaotic: { emoji: "🚨", label: "Chaotic", color: "text-black" },
  };
  const env = envConfig[data.environment] ?? envConfig.quiet;

  const loudnessConfig = {
    whisper: { label: "Whisper", bars: 1 },
    normal: { label: "Normal", bars: 2 },
    loud: { label: "Loud", bars: 3 },
    shouting: { label: "Shouting", bars: 4 },
  };
  const loud = loudnessConfig[data.loudness] ?? loudnessConfig.normal;

  return (
    <div
      id="acoustic-widget"
      className={`flex flex-col gap-3 rounded-2xl border p-4 transition-all duration-300 ${
        data.is_high_distress
          ? "border-black/30 bg-black/5"
          : "border-black/10 bg-white"
      }`}
    >
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-widest font-bold text-black/50">
          Acoustic Analysis
        </span>
        {data.is_high_distress && (
          <span className="text-[10px] font-bold text-black">
            HIGH DISTRESS
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="flex items-center gap-2">
          <span className={`text-lg ${env.color}`}>{env.emoji}</span>
          <div>
            <p className="text-[10px] text-muted-foreground/60 uppercase">Env</p>
            <p className={`text-xs font-semibold ${env.color}`}>{env.label}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-end gap-0.5 h-4">
            {[1, 2, 3, 4].map((b) => (
              <div
                key={b}
                className={`w-1 rounded-t-sm transition-all ${
                  b <= loud.bars ? "bg-black" : "bg-black/10"
                }`}
                style={{ height: `${b * 25}%` }}
              />
            ))}
          </div>
          <div>
            <p className="text-[10px] text-black/50 uppercase">Volume</p>
            <p className="text-xs font-semibold text-black/80">{loud.label}</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export function TranscriptFeed({ entries }: { entries: TranscriptEntry[] }) {
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
          <p className="text-sm text-black/40 italic">
            Call transcript will appear here...
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
                ? "bg-black text-white border border-black rounded-bl-md"
                : "bg-white text-black border border-black/10 rounded-br-md"
              }
            `}
          >
            <div className="flex items-center gap-2 mb-1.5">
              <span className="text-[10px] font-bold uppercase tracking-wider opacity-60">
                {entry.sender === "citizen" ? "👤 Citizen" : "🤖 VaakSetu AI"}
              </span>
              <span className="text-[9px] text-black/40 font-mono">
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
