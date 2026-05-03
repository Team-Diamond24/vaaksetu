import { useEffect, useRef } from "react";

interface Props {
  analyser: AnalyserNode | null;
  isActive: boolean;
}

/* ------------------------------------------------------------------ */
/*  Gradient palette — teal → blue → violet                           */
/* ------------------------------------------------------------------ */
const BAR_COLORS = [
  "#06b6d4", "#0891b2", "#0e7490", "#0284c7",
  "#2563eb", "#4f46e5", "#7c3aed", "#8b5cf6",
  "#a855f7", "#c084fc",
];

function colorAt(i: number, total: number): string {
  const t = i / Math.max(total - 1, 1);
  const idx = Math.min(Math.floor(t * (BAR_COLORS.length - 1)), BAR_COLORS.length - 1);
  return BAR_COLORS[idx];
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */
export function AudioVisualizer({ analyser, isActive }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    /* hi-DPI scaling */
    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.scale(dpr, dpr);
    };
    resize();
    window.addEventListener("resize", resize);

    const bufLen = analyser?.frequencyBinCount ?? 64;
    const dataArr = new Uint8Array(bufLen);
    const smooth = new Float32Array(bufLen); // smoothed values

    const draw = () => {
      rafRef.current = requestAnimationFrame(draw);
      const W = canvas.getBoundingClientRect().width;
      const H = canvas.getBoundingClientRect().height;
      ctx.clearRect(0, 0, W, H);

      /* fill freq data */
      if (analyser && isActive) {
        analyser.getByteFrequencyData(dataArr);
      } else {
        dataArr.fill(0);
      }

      const barCount = Math.min(bufLen, 64);
      const gap = 3;
      const barW = Math.max((W - gap * (barCount - 1)) / barCount, 2);
      const maxH = H * 0.82;

      for (let i = 0; i < barCount; i++) {
        /* damped smoothing */
        const target = (dataArr[i] / 255) * maxH;
        smooth[i] += (target - smooth[i]) * 0.25;
        const h = Math.max(smooth[i], 2);

        const x = i * (barW + gap);
        const y = H / 2 - h / 2;

        /* main bar */
        const color = colorAt(i, barCount);
        ctx.fillStyle = color;
        ctx.beginPath();
        const r = Math.min(barW / 2, 4);
        ctx.roundRect(x, y, barW, h, r);
        ctx.fill();

        /* glow */
        ctx.save();
        ctx.shadowColor = color;
        ctx.shadowBlur = 10;
        ctx.fillStyle = color;
        ctx.globalAlpha = 0.35;
        ctx.beginPath();
        ctx.roundRect(x, y, barW, h, r);
        ctx.fill();
        ctx.restore();
      }
    };

    draw();
    return () => {
      cancelAnimationFrame(rafRef.current);
      window.removeEventListener("resize", resize);
    };
  }, [analyser, isActive]);

  return (
    <canvas
      ref={canvasRef}
      className="w-full h-32 rounded-xl"
      style={{ imageRendering: "auto" }}
    />
  );
}
