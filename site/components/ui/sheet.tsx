"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ComponentProps } from "react";
import { cn } from "./utils";

export const Sheet = Dialog.Root;
export const SheetTitle = Dialog.Title;
export const SheetDescription = Dialog.Description;

export function SheetContent({ children, className, ...props }: ComponentProps<typeof Dialog.Content>) {
  return <Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-40 bg-black/65" />
    <Dialog.Content className={cn("sheet fixed inset-y-0 right-0 z-50 w-full overflow-y-auto border-l border-border bg-sheet p-6 shadow-2xl sm:max-w-[780px] sm:p-8", className)} {...props}>
      {children}
      <Dialog.Close className="sheet-close" aria-label="Close details"><X size={18} /></Dialog.Close>
    </Dialog.Content>
  </Dialog.Portal>;
}
