import { z } from "zod";

const mode = z.enum(["vanilla", "internet", "skills"]);
const count = z.number().int().nonnegative();
const measure = z.number().nonnegative().nullable();
export const rowSchema = z.object({
  schema_version: z.literal(7),
  task_id: z.string().min(1),
  task_hash: z.string().min(1),
  skills_hash: z.string().min(1).nullable(),
  mode,
  agent: z.string().min(1).nullable(),
  model: z.string().min(1),
  effort: z.string().nullable(),
  trial: z.number().int().positive(),
  status: z.enum(["passed", "failed", "error"]),
  checks: z.record(z.string(), z.object({ passed: z.boolean(), reason: z.string().min(1) })),
  error_kind: z.string().nullable(),
  error_reason: z.string().nullable(),
  limit: z.object({ type: z.string(), limit: z.number(), reason: z.string().nullable() }).nullable(),
  total_tokens: count,
  model_cost_usd: measure,
  judge_cost_usd: measure,
  total_seconds: measure,
  working_seconds: measure,
  cost_source: z.string(),
  paid_by: z.enum(["plan", "api_key", "free"]),
  judge: z.object({ model: z.string(), effort: z.string().nullable() }).nullable(),
  judge_paid_by: z.enum(["plan", "api_key", "free"]).nullable(),
  trajectory_url: z.string().regex(/^(https?:\/\/|\/(?!\/))/).nullable(),
}).refine((row) => row.mode === "skills" ? row.skills_hash !== null : row.skills_hash === null,
  { message: "Skills rows require a pack hash; other modes require null." });


export type Row = z.infer<typeof rowSchema>;
