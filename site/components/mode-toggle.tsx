"use client";

import type { Mode } from "../src/board";
import { ToggleGroup, ToggleGroupItem } from "./ui/toggle-group";

export const modeNames: Record<Mode, string> = { internet: "Internet", skills: "Internet + Skills", vanilla: "Model only" };

export function ModeToggle({ mode, onChange, label = "Which results", disabled = [] }: { mode: Mode; onChange: (mode: Mode) => void; label?: string; disabled?: Mode[] }) {
  const change = (value: string) => { if (value) onChange(value as Mode); };
  return <div className="mode-toggle" role="group" aria-label={label}>
    <ToggleGroup type="single" value={mode} onValueChange={change} aria-label="Agent modes">
      <ToggleGroupItem value="internet" disabled={disabled.includes("internet")}>Internet</ToggleGroupItem>
      <ToggleGroupItem value="skills" disabled={disabled.includes("skills")} className="border-l border-border-strong">Internet + Skills</ToggleGroupItem>
    </ToggleGroup>
    <span className="mode-separator" aria-hidden="true" />
    <ToggleGroup type="single" value={mode} onValueChange={change} className="border-dashed" aria-label="Bare model mode">
      <ToggleGroupItem value="vanilla" disabled={disabled.includes("vanilla")}>Model only</ToggleGroupItem>
    </ToggleGroup>
  </div>;
}
