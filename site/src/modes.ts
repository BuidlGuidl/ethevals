import type { Mode } from "./board";

const liveModes: readonly Mode[] = ["internet", "vanilla"];

export const isLiveMode = (value: string | null): value is Mode => liveModes.some((mode) => mode === value);
export const readMode = (value: string | null): Mode => liveModes.find((mode) => mode === value) ?? "internet";
