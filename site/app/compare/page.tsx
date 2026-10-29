import { loadBoard } from "../../src/load";
import { pageMetadata } from "../../src/metadata";
import Compare from "./compare";

export const metadata = pageMetadata("Compare configurations · ETH Evals", "/compare/");
export default function Page() { return <Compare data={loadBoard()} />; }
