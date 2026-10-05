import { loadBoard } from "../../src/load";
import Compare from "./compare";

export const metadata = { title: "Compare configurations · ETH Evals" };
export default function Page() { return <Compare data={loadBoard()} />; }
