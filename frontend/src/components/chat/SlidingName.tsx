import { useState, useEffect, useRef } from "react";

interface SlidingNameProps {
  name: string;
  maxChars?: number;
  className?: string;
}

export function SlidingName({ name, maxChars = 30, className = "" }: SlidingNameProps) {
  const [isHovered, setIsHovered] = useState(false);
  const [offset, setOffset] = useState(0);
  const animationRef = useRef<number | null>(null);
  const startTimeRef = useRef<number | null>(null);
  const directionRef = useRef<"forward" | "backward">("forward");

  useEffect(() => {
    if (name.length <= maxChars) {
      setOffset(0);
      return;
    }

    if (!isHovered) {
      // Reset to start when not hovered
      setOffset(0);
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
        animationRef.current = null;
      }
      startTimeRef.current = null;
      directionRef.current = "forward";
      return;
    }

    // Start animation when hovered
    const animate = (timestamp: number) => {
      if (!startTimeRef.current) {
        startTimeRef.current = timestamp;
      }

      const elapsed = timestamp - startTimeRef.current;
      const totalDuration = 4000; // 4 seconds for full cycle (2s forward, 2s backward)
      const halfDuration = totalDuration / 2;
      const maxOffset = name.length - maxChars;

      let progress: number;
      if (elapsed < halfDuration) {
        // Forward: slide to show the end
        directionRef.current = "forward";
        progress = Math.min(elapsed / halfDuration, 1);
        setOffset(Math.floor(maxOffset * progress));
      } else {
        // Backward: slide back to start
        directionRef.current = "backward";
        progress = Math.min((elapsed - halfDuration) / halfDuration, 1);
        setOffset(Math.floor(maxOffset * (1 - progress)));
      }

      if (elapsed >= totalDuration) {
        // Cycle complete, restart
        startTimeRef.current = timestamp;
        directionRef.current = "forward";
        setOffset(0);
      } else {
        animationRef.current = requestAnimationFrame(animate);
      }
    };

    animationRef.current = requestAnimationFrame(animate);

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
        animationRef.current = null;
      }
      startTimeRef.current = null;
    };
  }, [isHovered, name, maxChars]);

  if (name.length <= maxChars) {
    return <span className={className}>{name}</span>;
  }

  const displayText = name.substring(offset, offset + maxChars);

  return (
    <span
      className={className}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        display: "inline-block",
        overflow: "hidden",
        whiteSpace: "nowrap",
        transition: isHovered ? "none" : "all 0.3s ease",
      }}
      title={name}
    >
      {displayText}
      {!isHovered && offset === 0 && <span className="opacity-50">...</span>}
    </span>
  );
}

