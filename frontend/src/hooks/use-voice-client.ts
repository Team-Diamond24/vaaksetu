import { useCallback, useEffect, useRef, useState } from "react";
import { arrayBufferToBase64, base64ToArrayBuffer } from "@/lib/audio-utils";
import type { AcousticData, CallMetadata, CallState, ClientMessage, ReasoningOutput, ServerMessage } from "@/types";

/* ------------------------------------------------------------------ */
/*  Public state exposed by the hook                                   */
/* ------------------------------------------------------------------ */
export interface VoiceClientState {
  isConnected: boolean;
  isRecording: boolean;
  callActive: boolean;
  isAiSpeaking: boolean;
  isAiMuted: boolean;
  isThinking: boolean;
  callState: CallState;
  error: string | null;
  metadata: CallMetadata | null;
  transcript: string;
  reasoning: ReasoningOutput | null;
  acousticData: AcousticData | null;
}

export interface VoiceClientActions {
  startCall: () => Promise<void>;
  stopCall: () => void;
  toggleTakeover: () => void;
  analyserNode: React.RefObject<AnalyserNode | null>;
}

/* ------------------------------------------------------------------ */
/*  Hook                                                               */
/* ------------------------------------------------------------------ */
export function useVoiceClient(): VoiceClientState & VoiceClientActions {
  /* ---- state ---- */
  const [isConnected, setIsConnected] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [callActive, setCallActive] = useState(false);
  const [isAiSpeaking, setIsAiSpeaking] = useState(false);
  const [isAiMuted, setIsAiMuted] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [metadata, setMetadata] = useState<CallMetadata | null>(null);
  const [transcript, setTranscript] = useState("");
  const [reasoning, setReasoning] = useState<ReasoningOutput | null>(null);
  const [callState, setCallState] = useState<CallState>("LISTENING");
  const [acousticData, setAcousticData] = useState<AcousticData | null>(null);

  /* ---- refs (never cause re-renders) ---- */
  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const workletRef = useRef<AudioWorkletNode | null>(null);
  const analyserNode = useRef<AnalyserNode | null>(null);
  const playbackSourceRef = useRef<AudioBufferSourceNode | null>(null);
  const sessionIdRef = useRef<string>("");

  /* ---- TTS audio queue refs ---- */
  const audioChunkQueue = useRef<ArrayBuffer[]>([]);
  const ttsAudioRef = useRef<HTMLAudioElement | null>(null);
  const ttsBlobUrlRef = useRef<string | null>(null);
  const ttsMediaSourceRef = useRef<MediaSource | null>(null);
  const ttsSourceBufferRef = useRef<SourceBuffer | null>(null);
  const ttsStreamDoneRef = useRef(false);
  const ttsJitterTimerRef = useRef<number | null>(null);
  const wasUserSpeakingRef = useRef(false);

  /* ---- helpers ---- */
  const send = useCallback((msg: ClientMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  /** Clean up any active TTS Blob URL to prevent memory leaks */
  const revokeTtsBlobUrl = useCallback(() => {
    if (ttsBlobUrlRef.current) {
      URL.revokeObjectURL(ttsBlobUrlRef.current);
      ttsBlobUrlRef.current = null;
    }
  }, []);

  const clearTtsJitterTimer = useCallback(() => {
    if (ttsJitterTimerRef.current !== null) {
      window.clearTimeout(ttsJitterTimerRef.current);
      ttsJitterTimerRef.current = null;
    }
  }, []);

  const maybeFinalizeTtsStream = useCallback(() => {
    const mediaSource = ttsMediaSourceRef.current;
    const sourceBuffer = ttsSourceBufferRef.current;
    if (!mediaSource || mediaSource.readyState !== "open" || !ttsStreamDoneRef.current) {
      return;
    }
    if (sourceBuffer?.updating) return;
    if (audioChunkQueue.current.length > 0) return;
    try {
      mediaSource.endOfStream();
    } catch {
      /* no-op */
    }
  }, []);

  const appendNextTtsChunk = useCallback(() => {
    const sourceBuffer = ttsSourceBufferRef.current;
    if (!sourceBuffer || sourceBuffer.updating) return;
    const next = audioChunkQueue.current.shift();
    if (!next) {
      maybeFinalizeTtsStream();
      return;
    }
    try {
      sourceBuffer.appendBuffer(next);
    } catch (err) {
      console.error("[VoiceClient] sourceBuffer append error:", err);
      maybeFinalizeTtsStream();
    }
  }, [maybeFinalizeTtsStream]);

  const ensureStreamingTtsPlayback = useCallback(() => {
    if (ttsAudioRef.current || ttsMediaSourceRef.current) return;

    revokeTtsBlobUrl();
    const mediaSource = new MediaSource();
    ttsMediaSourceRef.current = mediaSource;

    const url = URL.createObjectURL(mediaSource);
    ttsBlobUrlRef.current = url;

    const audio = new Audio(url);
    audio.preload = "auto";
    ttsAudioRef.current = audio;
    setIsAiSpeaking(true);

    mediaSource.addEventListener("sourceopen", () => {
      if (mediaSource.readyState !== "open") return;
      try {
        const sourceBuffer = mediaSource.addSourceBuffer("audio/mpeg");
        sourceBuffer.mode = "sequence";
        ttsSourceBufferRef.current = sourceBuffer;
        sourceBuffer.addEventListener("updateend", appendNextTtsChunk);
        appendNextTtsChunk();
      } catch (err) {
        console.error("[VoiceClient] MediaSource init error:", err);
        setIsAiSpeaking(false);
      }
    });

    audio.onended = () => {
      setIsAiSpeaking(false);
      ttsAudioRef.current = null;
      ttsMediaSourceRef.current = null;
      ttsSourceBufferRef.current = null;
      revokeTtsBlobUrl();
    };

    audio.onerror = () => {
      console.error("[VoiceClient] TTS streaming playback error");
      setIsAiSpeaking(false);
      ttsAudioRef.current = null;
      ttsMediaSourceRef.current = null;
      ttsSourceBufferRef.current = null;
      revokeTtsBlobUrl();
    };

    audio.play().catch((e) => {
      console.error("[VoiceClient] TTS autoplay blocked:", e);
      setIsAiSpeaking(false);
    });
  }, [appendNextTtsChunk, revokeTtsBlobUrl]);

  /**
   * Barge-in: immediately kill ALL ongoing playback.
   * Stops both legacy AudioBufferSourceNode playback and streaming TTS.
   */
  const handleInterrupt = useCallback(() => {
    // Stop legacy BufferSource playback
    try {
      playbackSourceRef.current?.stop();
    } catch {
      /* already stopped */
    }
    playbackSourceRef.current = null;

    // Stop TTS HTMLAudioElement playback
    if (ttsAudioRef.current) {
      ttsAudioRef.current.pause();
      ttsAudioRef.current.currentTime = 0;
      ttsAudioRef.current.src = "";
      ttsAudioRef.current = null;
    }

    // Clear pending audio chunks
    audioChunkQueue.current = [];
    ttsStreamDoneRef.current = false;
    ttsMediaSourceRef.current = null;
    ttsSourceBufferRef.current = null;
    clearTtsJitterTimer();

    // Clean up blob URL
    revokeTtsBlobUrl();

    setIsAiSpeaking(false);
  }, [clearTtsJitterTimer, revokeTtsBlobUrl]);

  /** Decode Base64 audio from backend and play it (legacy single-shot) */
  const playAudio = useCallback(async (b64: string) => {
    const ctx = audioCtxRef.current;
    if (!ctx) return;
    try {
      const raw = base64ToArrayBuffer(b64);
      const audioBuffer = await ctx.decodeAudioData(raw);
      handleInterrupt(); // stop previous playback
      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(ctx.destination);
      source.onended = () => {
        playbackSourceRef.current = null;
      };
      playbackSourceRef.current = source;
      source.start();
    } catch (e) {
      console.error("[VoiceClient] playback error", e);
    }
  }, [handleInterrupt]);

  /** Route incoming WebSocket messages */
  const onWsMessage = useCallback(
    (ev: MessageEvent) => {
      try {
        const msg: ServerMessage = JSON.parse(ev.data);
        switch (msg.type) {
          case "interrupt":
            handleInterrupt();
            break;

          case "audio_playback":
            playAudio(msg.data);
            break;

          case "audio_chunk":
            // Queue incoming TTS bytes and start playback with small jitter buffer.
            audioChunkQueue.current.push(base64ToArrayBuffer(msg.data));
            ttsStreamDoneRef.current = false;
            ensureStreamingTtsPlayback();
            if (ttsJitterTimerRef.current === null) {
              ttsJitterTimerRef.current = window.setTimeout(() => {
                ttsJitterTimerRef.current = null;
                appendNextTtsChunk();
              }, 80);
            }
            break;

          case "audio_done":
            // Signal stream completion; flush remaining pending chunks.
            ttsStreamDoneRef.current = true;
            appendNextTtsChunk();
            break;

          case "metadata":
            setMetadata(msg.data);
            setIsAiMuted(Boolean(msg.data.is_muted));
            if (wasUserSpeakingRef.current && !msg.data.is_user_speaking) {
              setIsThinking(true);
            }
            wasUserSpeakingRef.current = msg.data.is_user_speaking;
            // Barge-in: if user starts speaking, stop AI audio
            if (msg.data.is_user_speaking) {
              setIsThinking(false);
              handleInterrupt();
            }
            // Human takeover immediately silences any in-progress AI speech.
            if (msg.data.is_muted) {
              handleInterrupt();
            }
            break;

          case "transcript":
            setTranscript(msg.text);
            setIsThinking(false);
            break;

          case "reasoning_update":
            setReasoning(msg.data);
            setIsThinking(false);
            break;

          case "state_change":
            setCallState(msg.state);
            break;

          case "acoustic_update":
            setAcousticData(msg.data);
            break;

          case "error":
            setError(msg.message);
            setIsThinking(false);
            break;
        }
      } catch {
        console.warn("[VoiceClient] unparseable WS message");
      }
    },
    [appendNextTtsChunk, ensureStreamingTtsPlayback, handleInterrupt, playAudio],
  );

  /* ---- start / stop ---- */
  const startCall = useCallback(async () => {
    setError(null);

    /* 1. Mic permission */
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
    } catch {
      setError("Microphone access denied");
      return;
    }
    streamRef.current = stream;

    /* 2. AudioContext (native sample rate for good visualizer) */
    const ctx = new AudioContext();
    audioCtxRef.current = ctx;

    /* 3. Analyser for visualizer */
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = 0.8;
    analyserNode.current = analyser;

    const source = ctx.createMediaStreamSource(stream);
    source.connect(analyser);

    /* 4. AudioWorklet for capture */
    try {
      await ctx.audioWorklet.addModule("/worklets/audio-capture-processor.js");
    } catch {
      setError("AudioWorklet not supported in this browser");
      stream.getTracks().forEach((t) => t.stop());
      return;
    }

    const worklet = new AudioWorkletNode(ctx, "audio-capture-processor", {
      processorOptions: { targetSampleRate: 16000 },
    });

    /* 5. Session id */
    const sid = crypto.randomUUID();
    sessionIdRef.current = sid;

    /* 6. WebSocket */
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/call`);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      send({ type: "start_call", session_id: sid });
    };
    ws.onmessage = onWsMessage;
    ws.onerror = () => setError("WebSocket error");
    ws.onclose = () => setIsConnected(false);

    /* 7. Wire worklet → base64 → WS */
    worklet.port.onmessage = (e) => {
      if (e.data?.type === "chunk") {
        const b64 = arrayBufferToBase64(e.data.pcm);
        send({ type: "audio_chunk", data: b64, session_id: sid });
      }
    };

    source.connect(worklet);
    worklet.connect(ctx.destination); // required to keep worklet alive
    workletRef.current = worklet;

    setIsRecording(true);
    setCallActive(true);
  }, [send, onWsMessage]);

  const stopCall = useCallback(() => {
    /* signal backend */
    if (sessionIdRef.current) {
      send({ type: "end_call", session_id: sessionIdRef.current });
    }

    /* tear down worklet */
    workletRef.current?.disconnect();
    workletRef.current = null;

    /* stop mic */
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;

    /* stop all playback (legacy + TTS) */
    handleInterrupt();

    /* close audio context */
    audioCtxRef.current?.close();
    audioCtxRef.current = null;
    analyserNode.current = null;

    /* close WS */
    wsRef.current?.close();
    wsRef.current = null;

    setIsRecording(false);
    setCallActive(false);
    setIsConnected(false);
    setMetadata(null);
    setTranscript("");
    setReasoning(null);
    setCallState("LISTENING");
    setAcousticData(null);
    setIsAiMuted(false);
    setIsThinking(false);
    wasUserSpeakingRef.current = false;
  }, [send, handleInterrupt]);

  const toggleTakeover = useCallback(() => {
    if (!sessionIdRef.current) return;
    send({ type: "TOGGLE_TAKEOVER", session_id: sessionIdRef.current });
  }, [send]);

  /* cleanup on unmount */
  useEffect(() => stopCall, [stopCall]);

  return {
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
  };
}
