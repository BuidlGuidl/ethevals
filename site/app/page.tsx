import { loadBoard } from "../src/load";
import Board from "./board";

export default function Page() {
  return <Board data={loadBoard()} />;
}
