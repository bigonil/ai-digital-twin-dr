import { useState, useRef, useCallback, useEffect } from 'react';

/**
 * Custom hook for managing timeline animation state (play/pause/speed/seek)
 * @param {number} totalDuration - Total duration of the simulation in milliseconds
 * @returns {Object} Playback state and control methods
 */
export function useSimulationPlayback(totalDuration) {
  const [simulationTime, setSimulationTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState(1.0);

  const lastTimeRef = useRef(Date.now());
  const animationFrameRef = useRef(null);

  // Calculate progress as a value between 0 and 1
  const progress = totalDuration > 0 ? simulationTime / totalDuration : 0;

  // Animation loop using requestAnimationFrame
  useEffect(() => {
    if (!isPlaying) {
      return;
    }

    const animate = () => {
      const now = Date.now();
      const deltaMs = now - lastTimeRef.current;
      lastTimeRef.current = now;

      setSimulationTime((prevTime) => {
        const newTime = prevTime + deltaMs * speed;
        return Math.min(newTime, totalDuration);
      });

      animationFrameRef.current = requestAnimationFrame(animate);
    };

    lastTimeRef.current = Date.now();
    animationFrameRef.current = requestAnimationFrame(animate);

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [isPlaying, speed, totalDuration]);

  // Auto-pause when reaching the end
  useEffect(() => {
    if (simulationTime >= totalDuration && totalDuration > 0 && isPlaying) {
      setIsPlaying(false);
    }
  }, [simulationTime, totalDuration, isPlaying]);

  // Control callbacks
  const play = useCallback(() => {
    setIsPlaying(true);
  }, []);

  const pause = useCallback(() => {
    setIsPlaying(false);
  }, []);

  const togglePlayPause = useCallback(() => {
    setIsPlaying((prev) => !prev);
  }, []);

  const rewind = useCallback(() => {
    setSimulationTime(0);
    setIsPlaying(false);
  }, []);

  const seek = useCallback((newTime) => {
    // Clamp the new time between 0 and totalDuration
    const clampedTime = Math.max(0, Math.min(newTime, totalDuration));
    setSimulationTime(clampedTime);
  }, [totalDuration]);

  const changeSpeed = useCallback((newSpeed) => {
    // Clamp speed between 0.25 and 2.0
    const clampedSpeed = Math.max(0.25, Math.min(newSpeed, 2.0));
    setSpeed(clampedSpeed);
  }, []);

  return {
    simulationTime,
    isPlaying,
    speed,
    progress,
    play,
    pause,
    togglePlayPause,
    rewind,
    seek,
    changeSpeed,
    totalDuration,
  };
}
