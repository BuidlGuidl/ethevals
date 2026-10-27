"use client";

import { useState } from "react";
import type { Mode } from "../src/board";
import { modeNames } from "../src/labels";
import { isLiveMode } from "../src/modes";
import { ToggleGroup, ToggleGroupItem } from "./ui/toggle-group";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";

const descriptions = {
  vanilla: "Measures what the model knows from pre-training, with a plain call to the provider.",
  skills: "Measures whether giving agents skills makes them better at Ethereum work.",
};

function UpcomingMode({ value }: { value: keyof typeof descriptions }) {
  const [open, setOpen] = useState(false);
  const disabled = !isLiveMode(value);
  const button = <ToggleGroupItem value={value} disabled={disabled} className="disabled:pointer-events-none">{modeNames[value]}</ToggleGroupItem>;
  if (!disabled) return button;
  // Touch screens have no hover, so a tap opens the tooltip too. preventDefault skips Radix's close on click.
  return <Tooltip open={open} onOpenChange={setOpen} disableHoverableContent><TooltipTrigger asChild>
    <span className="inline-flex" tabIndex={0} onClick={(event) => { event.preventDefault(); setOpen(true); }}>{button}</span></TooltipTrigger>
    <TooltipContent className="max-w-80"><span className="badge">Coming soon</span><p className="mt-2">{descriptions[value]}</p></TooltipContent>
  </Tooltip>;
}

export function ModeToggle({ mode, onChange, label = "Which results" }: { mode: Mode; onChange: (mode: Mode) => void; label?: string }) {
  const change = (value: string) => { if (isLiveMode(value)) onChange(value); };
  return <div className="mode-toggle" role="group" aria-label={label}>
    <ToggleGroup type="single" value={mode} onValueChange={change} aria-label="Agent modes">
      <ToggleGroupItem value="internet">{modeNames.internet}</ToggleGroupItem>
      <span className="inline-flex border-l border-border-strong"><UpcomingMode value="skills" /></span>
    </ToggleGroup>
    <span className="mode-separator" aria-hidden="true" />
    <ToggleGroup type="single" value={mode} onValueChange={change} className="border-dashed" aria-label="Bare model mode">
      <UpcomingMode value="vanilla" />
    </ToggleGroup>
  </div>;
}
