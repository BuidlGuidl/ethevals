"use client";

import { useState } from "react";
import type { Mode } from "../src/board";
import { modelOnlyNote, modeNames } from "../src/labels";
import { isLiveMode } from "../src/modes";
import { ToggleGroup, ToggleGroupItem } from "./ui/toggle-group";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";

const descriptions = {
  vanilla: modelOnlyNote,
  skills: "Measures whether giving agents skills makes them better at Ethereum work.",
};
// Each tab draws its own border: solid when live, dashed when coming soon.
const edge = "border border-border-strong";

function UpcomingMode({ value }: { value: keyof typeof descriptions }) {
  const [open, setOpen] = useState(false);
  const disabled = !isLiveMode(value);
  const button = <ToggleGroupItem value={value} disabled={disabled} className={disabled ? "disabled:pointer-events-none" : edge}>{modeNames[value]}</ToggleGroupItem>;
  if (!disabled) return button;
  // Touch screens have no hover, so a tap opens the tooltip too. preventDefault skips Radix's close on click.
  return <Tooltip open={open} onOpenChange={setOpen} disableHoverableContent><TooltipTrigger asChild>
    <span className={`inline-flex border-dashed ${edge}`} tabIndex={0} onClick={(event) => { event.preventDefault(); setOpen(true); }}>{button}</span></TooltipTrigger>
    <TooltipContent className="max-w-80"><span className="badge">Coming soon</span><p className="mt-2">{descriptions[value]}</p></TooltipContent>
  </Tooltip>;
}

export function ModeToggle({ mode, onChange, label = "Which results" }: { mode: Mode; onChange: (mode: Mode) => void; label?: string }) {
  const change = (value: string) => { if (isLiveMode(value)) onChange(value); };
  return <div className="mode-toggle" role="group" aria-label={label}>
    <ToggleGroup type="single" value={mode} onValueChange={change} className="border-0 [&>*+*]:-ml-px" aria-label="Agent modes">
      <ToggleGroupItem value="internet" className={edge}>{modeNames.internet}</ToggleGroupItem>
      <UpcomingMode value="skills" />
    </ToggleGroup>
    <span className="mode-separator" aria-hidden="true" />
    <ToggleGroup type="single" value={mode} onValueChange={change} className="border-0" aria-label="Bare model mode">
      <UpcomingMode value="vanilla" />
    </ToggleGroup>
  </div>;
}
