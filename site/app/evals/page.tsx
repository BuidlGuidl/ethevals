import { loadTaskCatalog } from "../../src/load";
import { pageMetadata } from "../../src/metadata";
import { Tasks } from "./tasks";

export const metadata = pageMetadata("Tasks · ETH Evals", "/evals/");

export default function Page() {
  return <Tasks tasks={loadTaskCatalog().evals} />;
}
