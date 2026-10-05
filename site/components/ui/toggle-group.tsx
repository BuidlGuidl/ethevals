"use client";

import * as ToggleGroupPrimitive from "@radix-ui/react-toggle-group";
import type { ComponentProps } from "react";
import { cn } from "./utils";

const toggleClass = "inline-flex items-center justify-center px-3 py-2 text-xs font-medium transition-colors hover:bg-tint focus-visible:outline-2 focus-visible:outline-accent disabled:opacity-40 data-[state=on]:bg-accent data-[state=on]:text-sheet";
export function ToggleGroup({ className, ...props }: ComponentProps<typeof ToggleGroupPrimitive.Root>) {
  return <ToggleGroupPrimitive.Root className={cn("inline-flex border border-border-strong", className)} {...props} />;
}
export function ToggleGroupItem({ className, ...props }: ComponentProps<typeof ToggleGroupPrimitive.Item>) {
  return <ToggleGroupPrimitive.Item className={cn(toggleClass, className)} {...props} />;
}
