"use client";
import { ShieldBan } from "lucide-react";
import { InfoHint } from "./scores";
import { setIgnoringRefusals } from "./url-state";

const why = [
  "Some providers stop trials mid-task with a safety filter.",
  "By default, two refusals in a row score 0%.",
  "Turn this on to leave refused trials out of the averages.",
];

// Board-wide switch. It sits at the right end of the toolbar.
export function RefusalSwitch({ ignoring }: { ignoring: boolean }) {
  return <div className="refusal-controls">
    <button type="button" role="switch" aria-checked={ignoring} className="refusal-switch" onClick={() => setIgnoringRefusals(!ignoring)}>
      <span className="refusal-switch-track" aria-hidden="true"><span /></span>Ignore refusals
    </button>
    <InfoHint label="Why ignore refusals" text={why} />
  </div>;
}

export function RefusalStrip({ text }: { text: string }) {
  return <p className="refusal-strip"><ShieldBan aria-hidden="true" />{text}</p>;
}
