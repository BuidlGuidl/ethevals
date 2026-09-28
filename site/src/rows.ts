import { z } from "zod";
import { pillars } from "./board";

const mode = z.enum(["vanilla", "internet", "skills"]);
const evalType = z.enum(["quiz", "scenario", "build", "act"]);
const count = z.number().int().nonnegative();
const measure = z.number().nonnegative().nullable();
export const rowSchema = z.object({
  schema_version: z.literal(3),
  eval_id: z.string().min(1),
  eval_hash: z.string().min(1),
  pillar: z.enum(pillars),
  type: evalType,
  mode,
  harness: z.string().min(1).nullable(),
  model: z.string().min(1),
  effort: z.string().nullable(),
  answer_kind: z.string().nullable(),
  epoch: z.number().int().positive(),
  status: z.enum(["passed", "failed", "error"]),
  passed: z.boolean().nullable(),
  checks: z.record(z.string(), z.object({ passed: z.boolean(), reason: z.string().min(1) })),
  error_kind: z.string().nullable(),
  error_reason: z.string().nullable(),
  limit: z.object({ type: z.string(), limit: z.number(), reason: z.string().nullable() }).nullable(),
  total_tokens: count,
  token_source: z.string(),
  model_cost_usd: measure,
  grader_cost_usd: measure,
  model_cost_source: z.string(),
  grader_cost_source: z.string(),
  total_seconds: measure,
  working_seconds: measure,
  log_file: z.string().min(1),
}).superRefine((row, context) => {
  const checks = Object.values(row.checks);
  const consistent = row.status === "error" ? row.passed === null
    : checks.length > 0 && row.passed === (row.status === "passed")
      && row.passed === checks.every((check) => check.passed);
  if (!consistent) context.addIssue({ code: "custom", message: "Status, verdict, and checks disagree." });
});


export type Row = z.infer<typeof rowSchema>;
