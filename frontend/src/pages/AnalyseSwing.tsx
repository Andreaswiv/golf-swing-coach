import { useRef, useState, type DragEvent, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import {
  ACCEPTED_EXTENSIONS,
  CLUBS,
  MAX_UPLOAD_MB,
  MAX_VIDEO_SECONDS,
  api,
  type CameraAngle,
  type Handedness,
} from "../api";
import { Camera, Check, Lock, Upload } from "lucide-react";
import CameraDiagram from "@/components/CameraDiagram";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/lib/utils";

function Step({ n, title, children, done }: { n: number; title: string; children: ReactNode; done: boolean }) {
  return (
    <Card className="gap-4 p-6" aria-labelledby={`step-${n}`} role="group">
      <h2 id={`step-${n}`} className="flex items-center gap-3 text-base">
        <span
          className={cn(
            "flex size-7 items-center justify-center rounded-full text-sm font-semibold transition-colors",
            done ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
          )}
        >
          {done ? <Check className="size-4" /> : n}
        </span>
        {title}
      </h2>
      <div>{children}</div>
    </Card>
  );
}

function validateFile(file: File): string | null {
  const name = file.name.toLowerCase();
  if (!ACCEPTED_EXTENSIONS.some((ext) => name.endsWith(ext))) {
    return `Use an MP4 or MOV file. This one is "${file.name}".`;
  }
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    return `This file is ${(file.size / 1024 / 1024).toFixed(0)} MB. The limit is ${MAX_UPLOAD_MB} MB; trim the clip to just the swing.`;
  }
  if (file.size === 0) return "This file is empty.";
  return null;
}

/** Length of a local video file in seconds, or null if this browser cannot read it. */
function readDuration(file: File): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const video = document.createElement("video");
    const done = (value: number | null) => {
      window.clearTimeout(timer);
      URL.revokeObjectURL(url);
      video.removeAttribute("src");
      resolve(value);
    };
    const timer = window.setTimeout(() => done(null), 5000);
    video.preload = "metadata";
    video.muted = true;
    video.onloadedmetadata = () => done(Number.isFinite(video.duration) ? video.duration : null);
    video.onerror = () => done(null);
    video.src = url;
  });
}

async function validateLength(file: File): Promise<string | null> {
  // The analysis service checks too; this saves uploading a long file only to have it refused.
  const seconds = await readDuration(file);
  if (seconds !== null && seconds > MAX_VIDEO_SECONDS + 0.05) {
    return `This video is ${seconds.toFixed(1)} seconds long. The limit is ${MAX_VIDEO_SECONDS} seconds: trim it to just the swing (on an iPhone: Edit, then drag the ends of the timeline).`;
  }
  return null;
}

/** Select items cannot have an empty value, so "no club" has its own. */
const NO_CLUB = "none";

const ANGLES: { value: CameraAngle; title: string; text: string }[] = [
  {
    value: "face_on",
    title: "Face-on",
    text: "Camera in front of you, facing your chest. Shows weight shift, head and hip sway.",
  },
  {
    value: "down_the_line",
    title: "Down-the-line",
    text: "Camera behind the ball, looking along the target line. Shows posture and early extension.",
  },
];

export default function AnalyseSwing() {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [angle, setAngle] = useState<CameraAngle | null>(null);
  const [hand, setHand] = useState<Handedness | null>(null);
  const [club, setClub] = useState("");
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const [checking, setChecking] = useState(false);
  const picked = useRef<File | null>(null);

  async function pick(f: File | undefined) {
    if (!f) return;
    picked.current = f;
    const problem = validateFile(f);
    if (problem) {
      setFileError(problem);
      setFile(null);
      return;
    }
    setChecking(true);
    const tooLong = await validateLength(f);
    if (picked.current !== f) return; // another file was picked meanwhile
    setChecking(false);
    setFileError(tooLong);
    setFile(tooLong ? null : f);
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    pick(e.dataTransfer.files[0]);
  }

  const missing = checking ? "Checking the video…" : !file ? "Choose a video" : !angle ? "Choose a camera angle" : !hand ? "Choose your handedness" : null;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!file || !angle || !hand) return;
    setUploading(true);
    setSubmitError(null);
    setProgress(0);
    try {
      const analysis = await api.upload({ file, cameraAngle: angle, handedness: hand, club }, setProgress);
      navigate(`/analyses/${analysis.id}/processing`);
    } catch (err) {
      setSubmitError((err as Error).message);
      setUploading(false);
    }
  }

  const optionCls = (selected: boolean) =>
    cn(
      "cursor-pointer rounded-xl border bg-card transition-[border-color,box-shadow] has-[:focus-visible]:ring-[3px] has-[:focus-visible]:ring-ring/50",
      selected ? "border-leaf-4 shadow-[0_0_0_1px_var(--leaf-4)]" : "hover:border-muted-foreground/40",
    );

  return (
    <form onSubmit={onSubmit} className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_19rem]">
      <div className="space-y-4">
        <header className="mb-4">
          <h1 className="text-2xl">Analyse a swing</h1>
          <p className="mt-1 text-muted-foreground">Three quick steps, then the analysis runs on its own.</p>
        </header>

        <Step n={1} title="Choose your video" done={file !== null}>
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            className={cn(
              "flex cursor-pointer flex-col items-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors",
              dragging ? "border-leaf-4 bg-brand-soft" : file ? "border-leaf-3 bg-brand-soft/60" : "bg-muted/50 hover:border-muted-foreground/40",
            )}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".mp4,.mov,.m4v,video/mp4,video/quicktime"
              className="sr-only"
              onChange={(e) => pick(e.target.files?.[0])}
              aria-label="Swing video file"
            />
            <span className="flex size-11 items-center justify-center rounded-full border bg-card text-leaf-5 shadow-xs">
              {file ? <Check className="size-5" /> : <Upload className="size-5" />}
            </span>
            {file ? (
              <>
                <p className="mt-3 font-medium">{file.name}</p>
                <p className="tnum text-sm text-muted-foreground">{(file.size / 1024 / 1024).toFixed(1)} MB · click to change</p>
              </>
            ) : (
              <>
                <p className="mt-3 font-medium">Drop your video here, or click to browse</p>
                <p className="text-sm text-muted-foreground">MP4 or MOV, just the swing (at most {MAX_VIDEO_SECONDS} seconds)</p>
              </>
            )}
          </div>
          {fileError && (
            <p role="alert" className="mt-2 text-sm text-destructive">
              {fileError}
            </p>
          )}
        </Step>

        <Step n={2} title="Where was the camera?" done={angle !== null}>
          <fieldset>
            <legend className="sr-only">Camera angle</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              {ANGLES.map((a) => (
                <label key={a.value} className={cn(optionCls(angle === a.value), "p-4")}>
                  <input
                    type="radio"
                    name="angle"
                    value={a.value}
                    checked={angle === a.value}
                    onChange={() => setAngle(a.value)}
                    className="sr-only"
                  />
                  <span className="block rounded-lg bg-muted">
                    <CameraDiagram angle={a.value} />
                  </span>
                  <span className="mt-3 block font-semibold">{a.title}</span>
                  <span className="block text-sm text-muted-foreground">{a.text}</span>
                </label>
              ))}
            </div>
          </fieldset>
        </Step>

        <Step n={3} title="About your swing" done={hand !== null}>
          <div className="grid gap-5 sm:grid-cols-2">
            <div className="space-y-2">
              <Label id="hand-label">Handedness</Label>
              <ToggleGroup
                type="single"
                variant="outline"
                aria-labelledby="hand-label"
                value={hand ?? ""}
                onValueChange={(v) => v && setHand(v as Handedness)}
                className="w-full"
              >
                <ToggleGroupItem value="right" className="flex-1">
                  Right-handed
                </ToggleGroupItem>
                <ToggleGroupItem value="left" className="flex-1">
                  Left-handed
                </ToggleGroupItem>
              </ToggleGroup>
            </div>

            <div className="space-y-2">
              <Label htmlFor="club">
                Club <span className="font-normal text-muted-foreground">(optional)</span>
              </Label>
              <Select value={club || NO_CLUB} onValueChange={(v) => setClub(v === NO_CLUB ? "" : v)}>
                <SelectTrigger id="club" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_CLUB}>Not specified</SelectItem>
                  {CLUBS.map((c) => (
                    <SelectItem key={c} value={c}>
                      {c}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </Step>

        <div className="flex flex-wrap items-center gap-4 pt-2">
          <Button type="submit" size="lg" disabled={uploading || missing !== null} className="min-w-40">
            {uploading ? `Uploading… ${Math.round(progress * 100)}%` : "Start analysis"}
          </Button>
          {missing && !uploading && (
            <p className="text-sm text-muted-foreground">{checking ? missing : `${missing} to continue.`}</p>
          )}
          {submitError && (
            <p role="alert" className="text-sm text-destructive">
              {submitError}
            </p>
          )}
        </div>
      </div>

      <aside className="space-y-4 lg:pt-[4.25rem]">
        <Card className="gap-3 p-6">
          <h2 className="flex items-center gap-2 text-base">
            <Camera className="size-5 text-leaf-4" />
            Tips for a good video
          </h2>
          <ul className="space-y-2.5 text-sm text-muted-foreground">
            {[
              "Record at 60 fps or more; 120 fps is better. Slow motion works too: trim off the normal-speed start and end so the swing plays at one speed.",
              "Keep your whole body and the club in frame.",
              "Use a tripod or lean the phone against your bag.",
              "Film in good light with only you in the shot.",
              "Stand the camera at hip height, about 3 metres away.",
            ].map((t) => (
              <li key={t} className="flex gap-2">
                <Check className="mt-0.5 size-4 shrink-0 text-leaf-4" />
                {t}
              </li>
            ))}
          </ul>
        </Card>
        <p className="flex gap-2 px-1 text-sm text-muted-foreground">
          <Lock className="mt-0.5 size-4 shrink-0" />
          Your video is stored on this computer only. You can delete it at any time.
        </p>
      </aside>
    </form>
  );
}
