"use client";

import type { Mode } from "../src/board";
import { modeNames } from "../src/labels";
import { ToggleGroup, ToggleGroupItem } from "./ui/toggle-group";

export function ModeToggle({ mode, onChange, label = "Which results" }: { mode: Mode; onChange: (mode: Mode) => void; label?: string }) {
  const change = (value: string) => { if (value) onChange(value as Mode); };
  return <div className="mode-toggle" role="group" aria-label={label}>
    <ToggleGroup type="single" value={mode} onValueChange={change} aria-label="Agent modes">
      <ToggleGroupItem value="internet">{modeNames.internet}</ToggleGroupItem>
      <ToggleGroupItem value="skills" className="border-l border-border-strong">{modeNames.skills}</ToggleGroupItem>
    </ToggleGroup>
    <span className="mode-separator" aria-hidden="true" />
    <ToggleGroup type="single" value={mode} onValueChange={change} className="border-dashed" aria-label="Bare model mode">
      <ToggleGroupItem value="vanilla">{modeNames.vanilla}</ToggleGroupItem>
    </ToggleGroup>
  </div>;
}
