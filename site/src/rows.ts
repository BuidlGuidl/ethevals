import { z } from "zod";

const mode = z.enum(["vanilla", "internet", "skills"]);
const evalType = z.enum(["quiz", "build", "act"]);
const count = z.number().int().nonnegative();
const measure = z.number().nonnegative().nullable();
export const rowSchema = z.object({
  schema_version: z.literal(4),
  eval_id: z.string().min(1),
  eval_hash: z.string().min(1),
  type: evalType,
  mode,
  harness: z.string().min(1).nullable(),
  model: z.string().min(1),
  effort: z.string().nullable(),
  epoch: z.number().int().positive(),
  status: z.enum(["passed", "failed", "error"]),
  checks: z.record(z.string(), z.object({ passed: z.boolean(), reason: z.string().min(1) })),
  error_kind: z.string().nullable(),
  error_reason: z.string().nullable(),
  limit: z.object({ type: z.string(), limit: z.number(), reason: z.string().nullable() }).nullable(),
  total_tokens: count,
  model_cost_usd: measure,
  grader_cost_usd: measure,
  total_seconds: measure,
  working_seconds: measure,
  cost_source: z.string(),
  log_url: z.string().regex(/^(https?:\/\/|\/(?!\/))/).nullable(),
});


export type Row = z.infer<typeof rowSchema>;
