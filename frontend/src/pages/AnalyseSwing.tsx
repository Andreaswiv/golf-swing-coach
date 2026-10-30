import React, { useRef, useState, type DragEvent, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  ACCEPTED_EXTENSIONS,
  CLUBS,
  MAX_UPLOAD_MB,
  api,
  type CameraAngle,
  type Handedness,
} from "../api";
import CameraDiagram from "../components/CameraDiagram";
import { CameraIcon, CheckIcon, LockIcon, UploadIcon } from "../components/icons";

function Step({ n, title, children, done }: { n: number; title: string; children: React.ReactNode; done: boolean }) {
  return (
    <section className="card p-5 sm:p-6" aria-labelledby={`step-${n}`}>
      <h2 id={`step-${n}`} className="flex items-center gap-3 text-lg">
        <span
          className={`flex h-7 w-7 items-center justify-center rounded-full text-sm font-semibold ${
            done ? "bg-brand text-white" : "bg-subtle text-mute"
          }`}
        >
          {done ? <CheckIcon className="h-4 w-4" /> : n}
        </span>
        {title}
      </h2>
      <div className="mt-4">{children}</div>
    </section>
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

  function pick(f: File | undefined) {
    if (!f) return;
    const problem = validateFile(f);
    setFileError(problem);
    setFile(problem ? null : f);
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    pick(e.dataTransfer.files[0]);
  }

  const missing = !file ? "Choose a video" : !angle ? "Choose a camera angle" : !hand ? "Choose your handedness" : null;

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
    `cursor-pointer rounded-xl border-2 transition-colors has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-brand ${
      selected ? "border-brand bg-brand-soft/60" : "border-line bg-surface hover:border-mute/50"
    }`;

  return (
    <form onSubmit={onSubmit} className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_19rem]">
      <div className="space-y-5">
        <header className="mb-2">
          <h1 className="text-3xl">Analyse a swing</h1>
          <p className="mt-1 text-mute">Three quick steps, then the analysis takes about a minute.</p>
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
            className={`flex cursor-pointer flex-col items-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
              dragging ? "border-brand bg-brand-soft" : file ? "border-brand/40 bg-brand-soft/40" : "border-line bg-canvas hover:border-mute/50"
            }`}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".mp4,.mov,.m4v,video/mp4,video/quicktime"
              className="sr-only"
              onChange={(e) => pick(e.target.files?.[0])}
              aria-label="Swing video file"
            />
            <span className="flex h-12 w-12 items-center justify-center rounded-full bg-surface text-brand shadow-sm">
              {file ? <CheckIcon /> : <UploadIcon />}
            </span>
            {file ? (
              <>
                <p className="mt-3 font-medium">{file.name}</p>
                <p className="tnum text-sm text-mute">{(file.size / 1024 / 1024).toFixed(1)} MB · click to change</p>
              </>
            ) : (
              <>
                <p className="mt-3 font-medium">Drop your video here, or click to browse</p>
                <p className="text-sm text-mute">MP4 or MOV, just the swing (a few seconds)</p>
              </>
            )}
          </div>
          {fileError && (
            <p role="alert" className="mt-2 text-sm text-bad">
              {fileError}
            </p>
          )}
        </Step>

        <Step n={2} title="Where was the camera?" done={angle !== null}>
          <fieldset>
            <legend className="sr-only">Camera angle</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              {ANGLES.map((a) => (
                <label key={a.value} className={`${optionCls(angle === a.value)} p-4`}>
                  <input
                    type="radio"
                    name="angle"
                    value={a.value}
                    checked={angle === a.value}
                    onChange={() => setAngle(a.value)}
                    className="sr-only"
                  />
                  <span className="block rounded-lg bg-canvas">
                    <CameraDiagram angle={a.value} />
                  </span>
                  <span className="mt-3 block font-semibold">{a.title}</span>
                  <span className="block text-sm text-mute">{a.text}</span>
                </label>
              ))}
            </div>
          </fieldset>
        </Step>

        <Step n={3} title="About your swing" done={hand !== null}>
          <div className="grid gap-5 sm:grid-cols-2">
            <fieldset>
              <legend className="text-sm font-medium">Handedness</legend>
              <div className="mt-2 grid grid-cols-2 gap-2">
                {(["right", "left"] as const).map((h) => (
                  <label key={h} className={`${optionCls(hand === h)} px-3 py-2.5 text-center text-sm font-medium`}>
                    <input
                      type="radio"
                      name="hand"
                      value={h}
                      checked={hand === h}
                      onChange={() => setHand(h)}
                      className="sr-only"
                    />
                    {h === "right" ? "Right-handed" : "Left-handed"}
                  </label>
                ))}
              </div>
            </fieldset>

            <div>
              <label htmlFor="club" className="block text-sm font-medium">
                Club <span className="font-normal text-mute">(optional)</span>
              </label>
              <select
                id="club"
                value={club}
                onChange={(e) => setClub(e.target.value)}
                className="mt-2 w-full rounded-xl border-2 border-line bg-surface px-3 py-2.5 text-sm"
              >
                <option value="">Not specified</option>
                {CLUBS.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </Step>

        <div className="flex flex-wrap items-center gap-4 pt-2">
          <button type="submit" disabled={uploading || missing !== null} className="btn btn-primary px-6 py-3">
            {uploading ? `Uploading… ${Math.round(progress * 100)}%` : "Start analysis"}
          </button>
          {missing && !uploading && <p className="text-sm text-mute">{missing} to continue.</p>}
          {submitError && (
            <p role="alert" className="text-sm text-bad">
              {submitError}
            </p>
          )}
        </div>
      </div>

      <aside className="space-y-4 lg:pt-[4.5rem]">
        <div className="card p-5">
          <h2 className="flex items-center gap-2 text-base">
            <CameraIcon className="h-5 w-5 text-brand" />
            Tips for a good video
          </h2>
          <ul className="mt-3 space-y-2.5 text-sm text-mute">
            {[
              "Record at 60 fps or more; 120 fps is better. Slow motion works, but then tempo can\u2019t be measured.",
              "Keep your whole body and the club in frame.",
              "Use a tripod or lean the phone against your bag.",
              "Film in good light with only you in the shot.",
              "Stand the camera at hip height, about 3 metres away.",
            ].map((t) => (
              <li key={t} className="flex gap-2">
                <CheckIcon className="mt-0.5 h-4 w-4 shrink-0 text-brand" />
                {t}
              </li>
            ))}
          </ul>
        </div>
        <p className="flex gap-2 px-1 text-sm text-mute">
          <LockIcon className="mt-0.5 h-4 w-4 shrink-0" />
          Your video is stored on this computer only. You can delete it at any time.
        </p>
      </aside>
    </form>
  );
}
