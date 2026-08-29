"use client";

import { useEffect, useState } from "react";

/**
 * Measures an element with a ResizeObserver.
 *
 * Needed because react-force-graph renders its canvas into a plain div with no
 * intrinsic width. As a flex item that div collapses to width 0 — the canvas
 * can't size itself from a container whose width depends on the canvas. So we
 * measure the *outer* container and hand the graph explicit dimensions.
 *
 * Returns a callback ref (not a useRef) so it re-attaches when the measured
 * element mounts later than the hook — e.g. after an async fetch resolves and
 * the component swaps out of its loading state.
 */
export function useElementSize<T extends HTMLElement>() {
  const [node, setNode] = useState<T | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    if (!node) return;
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (!rect) return;
      // A hidden tab panel measures 0×0. Keeping the last real size means the
      // graph stays mounted while the user is on another tab, so returning to
      // it shows the layout exactly as they left it rather than re-simulating
      // from scratch. There is nothing worth rendering at zero size anyway.
      if (rect.width === 0 || rect.height === 0) return;
      setSize({ width: Math.round(rect.width), height: Math.round(rect.height) });
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [node]);

  return [setNode, size] as const;
}
