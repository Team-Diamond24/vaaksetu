import { useCallback, useEffect, useRef, useState } from "react";
import { arrayBufferToBase64, base64ToArrayBuffer } from "@/lib/audio-utils";
import type { CallMetadata, ClientMessage, ReasoningOutput, ServerMessage } from "@/types";

/* ------------------------------------------------------------------ */
/*  Public state exposed by the hook                                   */
/* ------------------------------------------------------------------ */
export interface VoiceClientState {
  isConnected: boolean;
  isRecording: boolean;
  callActive: boolean;
  isAiSpeaking: boolean;
  error: string | null;
  metadata: CallMetadata | null;
  transcript: string;
  reasoning: ReasoningOutput | null;
}

export interface VoiceClientActions {
  startCall: () => Promise<void>;
  stopCall: () => void;
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
  const [error, setError] = useState<string | null>(null);
  const [metadata, setMetadata] = useState<CallMetadata | null>(null);
  const [transcript, setTranscript] = useState("");
  const [reasoning, setReasoning] = useState<ReasoningOutput | null>(null);

  /* ---- refs (never cause re-renders) ---- */
  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const workletRef = useRef<AudioWorkletNode | null>(null);
  const analyserNode = useRef<AnalyserNode | null>(null);
  const playbackSourceRef = useRef<AudioBufferSourceNode | null>(null);
  const sessionIdRef = useRef<string>("");

  /* ---- TTS audio queue refs ---- */
  const audioChunkQueue = useRef<string[]>([]);
  const ttsAudioRef = useRef<HTMLAudioElement | null>(null);
  const ttsBlobUrlRef = useRef<string | null>(null);

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

  /**
   * Barge-in: immediately kill ALL ongoing playback.
   * Stops both legacy AudioBufferSourceNode playback and the new
   * HTMLAudioElement-based TTS queue.
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

    // Clean up blob URL
    revokeTtsBlobUrl();

    setIsAiSpeaking(false);
  }, [revokeTtsBlobUrl]);

  /**
   * Concatenate all queued Base64 chunks into a single MP3 blob,
   * then play it via an HTMLAudioElement (most reliable for MP3).
   */
  const flushAndPlayTtsQueue = useCallback(() => {
    const chunks = audioChunkQueue.current;
    if (chunks.length === 0) return;

    // Decode all Base64 chunks and concatenate into one ArrayBuffer
    const buffers = chunks.map((b64) => base64ToArrayBuffer(b64));
    const totalLength = buffers.reduce((acc, b) => acc + b.byteLength, 0);
    const combined = new Uint8Array(totalLength);
    let offset = 0;
    for (const buf of buffers) {
      combined.set(new Uint8Array(buf), offset);
      offset += buf.byteLength;
    }

    // Clear the queue
    audioChunkQueue.current = [];

    // Create Blob URL and play
    revokeTtsBlobUrl();
    const blob = new Blob([combined.buffer], { type: "audio/mpeg" });
    const url = URL.createObjectURL(blob);
    ttsBlobUrlRef.current = url;

    const audio = new Audio(url);
    ttsAudioRef.current = audio;
    setIsAiSpeaking(true);

    audio.onended = () => {
      setIsAiSpeaking(false);
      ttsAudioRef.current = null;
      revokeTtsBlobUrl();
    };

    audio.onerror = () => {
      console.error("[VoiceClient] TTS playback error");
      setIsAiSpeaking(false);
      ttsAudioRef.current = null;
      revokeTtsBlobUrl();
    };

    audio.play().catch((e) => {
      console.error("[VoiceClient] TTS autoplay blocked:", e);
      setIsAiSpeaking(false);
    });
  }, [revokeTtsBlobUrl]);

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
            // Queue incoming TTS audio chunk
            audioChunkQueue.current.push(msg.data);
            break;

          case "audio_done":
            // All TTS chunks received — concatenate and play
            flushAndPlayTtsQueue();
            break;

          case "metadata":
            setMetadata(msg.data);
            // Barge-in: if user starts speaking, stop AI audio
            if (msg.data.is_user_speaking) {
              handleInterrupt();
            }
            break;

          case "transcript":
            setTranscript(msg.text);
            break;

          case "reasoning_update":
            setReasoning(msg.data);
            break;

          case "error":
            setError(msg.message);
            break;
        }
      } catch {
        console.warn("[VoiceClient] unparseable WS message");
      }
    },
    [handleInterrupt, playAudio, flushAndPlayTtsQueue],
  );

  /* ---- start / stop ---- */
  const startCall = useCallback(async () => {
    setError(null);

    /* 1. Mic permission */
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
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
  }, [send, handleInterrupt]);

  /* cleanup on unmount */
  useEffect(() => stopCall, [stopCall]);

  return {
    isConnected,
    isRecording,
    callActive,
    isAiSpeaking,
    error,
    metadata,
    transcript,
    reasoning,
    startCall,
    stopCall,
    analyserNode,
  };
}
