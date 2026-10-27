import { loadTaskCatalog } from "../../src/load";
import { Tasks } from "./tasks";

export const metadata = { title: "Tasks · ETH Evals" };

export default function Page() {
  return <Tasks tasks={loadTaskCatalog().evals} />;
}
