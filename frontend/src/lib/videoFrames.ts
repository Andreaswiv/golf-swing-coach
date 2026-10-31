import { useEffect, useState } from "react";

/**
 * Still frames from a swing video, as JPEG object URLs: the homepage uses them as its images.
 * One hidden <video> per clip, one clip at a time (a page can ask for several), results cached
 * for the session. A frame is null when the browser cannot decode the video (e.g. HEVC in Chrome).
 */

const cache = new Map<string, Promise<(string | null)[]>>();
let queue: Promise<unknown> = Promise.resolve();

const once = (el: HTMLVideoElement, event: string, ms: number) =>
  new Promise<boolean>((resolve) => {
    const done = (ok: boolean) => {
      clearTimeout(timer);
      el.removeEventListener(event, onEvent);
      el.removeEventListener("error", onError);
      resolve(ok);
    };
    const onEvent = () => done(true);
    const onError = () => done(false);
    const timer = setTimeout(() => done(false), ms);
    el.addEventListener(event, onEvent);
    el.addEventListener("error", onError);
  });

async function grab(url: string, times: number[], width: number): Promise<(string | null)[]> {
  const video = document.createElement("video");
  video.muted = true;
  video.playsInline = true;
  video.preload = "auto";
  video.src = url;
  try {
    if (!(await once(video, "loadeddata", 15000)) || !video.videoWidth) return times.map(() => null);
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = Math.round((width * video.videoHeight) / video.videoWidth);
    const ctx = canvas.getContext("2d");
    const out: (string | null)[] = [];
    for (const t of times) {
      video.currentTime = Math.min(Math.max(t, 0), Math.max(0, video.duration - 0.05));
      if (!ctx || !(await once(video, "seeked", 8000))) {
        out.push(null);
        continue;
      }
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      // toBlob encodes off the main thread (toDataURL blocked the page for a moment per still).
      const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.82));
      out.push(blob ? URL.createObjectURL(blob) : null);
      await new Promise((resolve) => setTimeout(resolve, 0)); // let input and animations run between stills
    }
    return out;
  } finally {
    video.removeAttribute("src");
    video.load();
  }
}

export function captureFrames(url: string, times: number[], width = 720): Promise<(string | null)[]> {
  const key = `${url}|${times.map((t) => t.toFixed(3)).join(",")}|${width}`;
  let job = cache.get(key);
  if (!job) {
    job = queue.then(() => grab(url, times, width));
    queue = job.catch(() => undefined);
    cache.set(key, job);
  }
  return job;
}

/** Frames of `url` at `times` (seconds of video), or null while they are being grabbed. */
export function useVideoFrames(url: string | null, times: number[], width = 720): (string | null)[] | null {
  const key = url ? `${url}|${times.join(",")}` : "";
  const [frames, setFrames] = useState<{ key: string; frames: (string | null)[] } | null>(null);
  useEffect(() => {
    if (!url || times.length === 0) return;
    let alive = true;
    captureFrames(url, times, width).then((f) => alive && setFrames({ key, frames: f }));
    return () => {
      alive = false;
    };
  }, [key, width]); // `key` covers url and times

  return frames && frames.key === key ? frames.frames : null;
}
