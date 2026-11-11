import { Pause, Play } from "lucide-react";

export function BackgroundMotionToggle({ paused, onToggle, english = false }: { paused: boolean; onToggle: () => void; english?: boolean }) {
  return (
    <button type="button" className="background-motion-toggle" aria-pressed={paused} onClick={onToggle}>
      {paused ? <Play size={16} aria-hidden="true" /> : <Pause size={16} aria-hidden="true" />}
      {english ? "Pause background animation" : "暂停背景动画"}
    </button>
  );
}
