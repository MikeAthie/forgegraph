import { useEffect } from "react";
import type { Edge, Node } from "@xyflow/react";

import { useValidation } from "@/contexts/ValidationContext";

export function ValidationTrigger({ nodes, edges }: { nodes: Node[]; edges: Edge[] }) {
  const { validate } = useValidation();

  useEffect(() => {
    validate(nodes, edges);
  }, [nodes, edges, validate]);

  return null;
}
