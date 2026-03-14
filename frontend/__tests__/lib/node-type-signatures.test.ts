import {
  NODE_SIGNATURES,
  getNodeSignature,
  getPrimaryOutputType,
  getPrimaryInputType,
  hasMultipleOutputs,
  acceptsMultipleInputs,
} from "@/lib/node-type-signatures";
import { NODE_TYPES, type NodeType } from "@/lib/graph-types";
import { DataType } from "@/lib/data-types";

describe("node-type-signatures", () => {
  describe("NODE_SIGNATURES", () => {
    it("should have entries for all node types", () => {
      const allNodeTypes = Object.values(NODE_TYPES);
      allNodeTypes.forEach((nodeType) => {
        expect(NODE_SIGNATURES[nodeType]).toBeDefined();
      });
    });

    it("should have a signature entry for every registered node type", () => {
      const signatures = Object.keys(NODE_SIGNATURES);
      expect(signatures.length).toBe(Object.values(NODE_TYPES).length);
    });

    it("should have inputs and outputs arrays for each signature", () => {
      const allNodeTypes = Object.values(NODE_TYPES);
      allNodeTypes.forEach((nodeType) => {
        const signature = NODE_SIGNATURES[nodeType];
        expect(signature.inputs).toBeDefined();
        expect(Array.isArray(signature.inputs)).toBe(true);
        expect(signature.outputs).toBeDefined();
        expect(Array.isArray(signature.outputs)).toBe(true);
      });
    });

    it("should have description for each signature", () => {
      const allNodeTypes = Object.values(NODE_TYPES);
      allNodeTypes.forEach((nodeType) => {
        const signature = NODE_SIGNATURES[nodeType];
        expect(signature.description).toBeDefined();
        expect(typeof signature.description).toBe("string");
        expect(signature.description.length).toBeGreaterThan(0);
      });
    });

    describe("individual node signatures", () => {
      describe("AGENT node", () => {
        it("should have correct input signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.AGENT];
          expect(signature.inputs.length).toBe(1);
          expect(signature.inputs[0].name).toBe("context");
          expect(signature.inputs[0].type).toBe(DataType.JSON);
          expect(signature.inputs[0].required).toBe(false);
        });

        it("should have correct output signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.AGENT];
          expect(signature.outputs.length).toBe(1);
          expect(signature.outputs[0].name).toBe("result");
          expect(signature.outputs[0].type).toBe(DataType.ANY);
        });
      });

      describe("PROMPT node", () => {
        it("should have correct input signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.PROMPT];
          expect(signature.inputs.length).toBe(1);
          expect(signature.inputs[0].name).toBe("context");
          expect(signature.inputs[0].type).toBe(DataType.JSON);
          expect(signature.inputs[0].required).toBe(false);
        });

        it("should have correct output signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.PROMPT];
          expect(signature.outputs.length).toBe(1);
          expect(signature.outputs[0].name).toBe("response");
          expect(signature.outputs[0].type).toBe(DataType.TEXT);
        });
      });

      describe("HTTP node", () => {
        it("should have correct input signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.HTTP];
          expect(signature.inputs.length).toBe(2);
          expect(signature.inputs[0].name).toBe("body");
          expect(signature.inputs[0].type).toBe(DataType.JSON);
          expect(signature.inputs[1].name).toBe("headers");
          expect(signature.inputs[1].type).toBe(DataType.JSON);
        });

        it("should have correct output signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.HTTP];
          expect(signature.outputs.length).toBe(1);
          expect(signature.outputs[0].name).toBe("response");
          expect(signature.outputs[0].type).toBe(DataType.JSON);
        });
      });

      describe("TRANSFORM node", () => {
        it("should have correct input signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.TRANSFORM];
          expect(signature.inputs.length).toBe(1);
          expect(signature.inputs[0].name).toBe("input");
          expect(signature.inputs[0].type).toBe(DataType.ANY);
          expect(signature.inputs[0].required).toBe(true);
        });

        it("should have correct output signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.TRANSFORM];
          expect(signature.outputs.length).toBe(1);
          expect(signature.outputs[0].name).toBe("output");
          expect(signature.outputs[0].type).toBe(DataType.ANY);
        });
      });

      describe("BRANCH node", () => {
        it("should have correct input signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.BRANCH];
          expect(signature.inputs.length).toBe(1);
          expect(signature.inputs[0].name).toBe("value");
          expect(signature.inputs[0].type).toBe(DataType.ANY);
          expect(signature.inputs[0].required).toBe(true);
        });

        it("should have multiple outputs", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.BRANCH];
          expect(signature.outputs.length).toBe(2);
          expect(signature.outputs[0].name).toBe("true");
          expect(signature.outputs[0].type).toBe(DataType.ANY);
          expect(signature.outputs[1].name).toBe("false");
          expect(signature.outputs[1].type).toBe(DataType.ANY);
        });
      });

      describe("MERGE node", () => {
        it("should accept multiple inputs", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.MERGE];
          expect(signature.inputs.length).toBe(1);
          expect(signature.inputs[0].name).toBe("sources");
          expect(signature.inputs[0].type).toBe(DataType.ANY);
          expect(signature.inputs[0].multiple).toBe(true);
          expect(signature.inputs[0].required).toBe(true);
        });

        it("should have correct output signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.MERGE];
          expect(signature.outputs.length).toBe(1);
          expect(signature.outputs[0].name).toBe("merged");
          expect(signature.outputs[0].type).toBe(DataType.JSON);
        });
      });

      describe("OUTPUT node", () => {
        it("should have correct input signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.OUTPUT];
          expect(signature.inputs.length).toBe(1);
          expect(signature.inputs[0].name).toBe("data");
          expect(signature.inputs[0].type).toBe(DataType.ANY);
          expect(signature.inputs[0].required).toBe(true);
        });

        it("should have no outputs", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.OUTPUT];
          expect(signature.outputs.length).toBe(0);
        });
      });

      describe("HUMAN_GATE node", () => {
        it("should have correct input signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.HUMAN_GATE];
          expect(signature.inputs.length).toBe(1);
          expect(signature.inputs[0].name).toBe("data");
          expect(signature.inputs[0].type).toBe(DataType.ANY);
          expect(signature.inputs[0].required).toBe(false);
        });

        it("should have correct output signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.HUMAN_GATE];
          expect(signature.outputs.length).toBe(1);
          expect(signature.outputs[0].name).toBe("approved");
          expect(signature.outputs[0].type).toBe(DataType.ANY);
        });
      });

      describe("MEMORY node", () => {
        it("should have correct input signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.MEMORY];
          expect(signature.inputs.length).toBe(1);
          expect(signature.inputs[0].name).toBe("data");
          expect(signature.inputs[0].type).toBe(DataType.ANY);
          expect(signature.inputs[0].required).toBe(false);
        });

        it("should have correct output signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.MEMORY];
          expect(signature.outputs.length).toBe(1);
          expect(signature.outputs[0].name).toBe("retrieved");
          expect(signature.outputs[0].type).toBe(DataType.ANY);
        });
      });

      describe("OBSERVATION_SAVE node", () => {
        it("should have correct input signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.OBSERVATION_SAVE];
          expect(signature.inputs.length).toBe(1);
          expect(signature.inputs[0].name).toBe("context");
          expect(signature.inputs[0].type).toBe(DataType.ANY);
          expect(signature.inputs[0].required).toBe(false);
        });

        it("should have correct output signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.OBSERVATION_SAVE];
          expect(signature.outputs.length).toBe(1);
          expect(signature.outputs[0].name).toBe("output");
          expect(signature.outputs[0].type).toBe(DataType.JSON);
        });
      });

      describe("OBSERVATION_SEARCH node", () => {
        it("should have correct input signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.OBSERVATION_SEARCH];
          expect(signature.inputs.length).toBe(1);
          expect(signature.inputs[0].name).toBe("context");
          expect(signature.inputs[0].type).toBe(DataType.ANY);
          expect(signature.inputs[0].required).toBe(false);
        });

        it("should have correct output signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.OBSERVATION_SEARCH];
          expect(signature.outputs.length).toBe(1);
          expect(signature.outputs[0].name).toBe("output");
          expect(signature.outputs[0].type).toBe(DataType.JSON);
        });
      });

      describe("OBSERVATION_CONTEXT node", () => {
        it("should have correct input signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.OBSERVATION_CONTEXT];
          expect(signature.inputs.length).toBe(1);
          expect(signature.inputs[0].name).toBe("context");
          expect(signature.inputs[0].type).toBe(DataType.ANY);
          expect(signature.inputs[0].required).toBe(false);
        });

        it("should have correct output signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.OBSERVATION_CONTEXT];
          expect(signature.outputs.length).toBe(1);
          expect(signature.outputs[0].name).toBe("output");
          expect(signature.outputs[0].type).toBe(DataType.JSON);
        });
      });

      describe("OBSERVATION_TIMELINE node", () => {
        it("should have correct input signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.OBSERVATION_TIMELINE];
          expect(signature.inputs.length).toBe(1);
          expect(signature.inputs[0].name).toBe("context");
          expect(signature.inputs[0].type).toBe(DataType.ANY);
          expect(signature.inputs[0].required).toBe(false);
        });

        it("should have correct output signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.OBSERVATION_TIMELINE];
          expect(signature.outputs.length).toBe(1);
          expect(signature.outputs[0].name).toBe("output");
          expect(signature.outputs[0].type).toBe(DataType.JSON);
        });
      });

      describe("TOOL node", () => {
        it("should have correct input signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.TOOL];
          expect(signature.inputs.length).toBe(1);
          expect(signature.inputs[0].name).toBe("params");
          expect(signature.inputs[0].type).toBe(DataType.JSON);
          expect(signature.inputs[0].required).toBe(false);
        });

        it("should have correct output signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.TOOL];
          expect(signature.outputs.length).toBe(1);
          expect(signature.outputs[0].name).toBe("result");
          expect(signature.outputs[0].type).toBe(DataType.JSON);
        });
      });

      describe("SUBGRAPH node", () => {
        it("should have correct input signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.SUBGRAPH];
          expect(signature.inputs.length).toBe(1);
          expect(signature.inputs[0].name).toBe("input");
          expect(signature.inputs[0].type).toBe(DataType.JSON);
          expect(signature.inputs[0].required).toBe(false);
        });

        it("should have correct output signature", () => {
          const signature = NODE_SIGNATURES[NODE_TYPES.SUBGRAPH];
          expect(signature.outputs.length).toBe(1);
          expect(signature.outputs[0].name).toBe("output");
          expect(signature.outputs[0].type).toBe(DataType.JSON);
        });
      });
    });

    describe("port properties", () => {
      it("should have name and type for all ports", () => {
        const allNodeTypes = Object.values(NODE_TYPES);
        allNodeTypes.forEach((nodeType) => {
          const signature = NODE_SIGNATURES[nodeType];

          signature.inputs.forEach((input) => {
            expect(input.name).toBeDefined();
            expect(typeof input.name).toBe("string");
            expect(input.type).toBeDefined();
            expect(Object.values(DataType)).toContain(input.type);
          });

          signature.outputs.forEach((output) => {
            expect(output.name).toBeDefined();
            expect(typeof output.name).toBe("string");
            expect(output.type).toBeDefined();
            expect(Object.values(DataType)).toContain(output.type);
          });
        });
      });

      it("should have descriptions for all ports", () => {
        const allNodeTypes = Object.values(NODE_TYPES);
        allNodeTypes.forEach((nodeType) => {
          const signature = NODE_SIGNATURES[nodeType];

          signature.inputs.forEach((input) => {
            expect(input.description).toBeDefined();
            expect(typeof input.description).toBe("string");
          });

          signature.outputs.forEach((output) => {
            expect(output.description).toBeDefined();
            expect(typeof output.description).toBe("string");
          });
        });
      });
    });
  });

  describe("getNodeSignature", () => {
    it("should return correct signature for valid node type", () => {
      const signature = getNodeSignature(NODE_TYPES.PROMPT);
      expect(signature).toBeDefined();
      expect(signature?.inputs).toBeDefined();
      expect(signature?.outputs).toBeDefined();
    });

    it("should return signature for all node types", () => {
      const allNodeTypes = Object.values(NODE_TYPES);
      allNodeTypes.forEach((nodeType) => {
        const signature = getNodeSignature(nodeType);
        expect(signature).not.toBeNull();
      });
    });

    it("should return null for invalid node type", () => {
      const signature = getNodeSignature("invalid_type" as NodeType);
      expect(signature).toBeNull();
    });

    it("should return same object as in NODE_SIGNATURES", () => {
      const signature1 = getNodeSignature(NODE_TYPES.PROMPT);
      const signature2 = NODE_SIGNATURES[NODE_TYPES.PROMPT];
      expect(signature1).toBe(signature2);
    });
  });

  describe("getPrimaryOutputType", () => {
    it("should return TEXT for PROMPT node", () => {
      expect(getPrimaryOutputType(NODE_TYPES.PROMPT)).toBe(DataType.TEXT);
    });

    it("should return JSON for HTTP node", () => {
      expect(getPrimaryOutputType(NODE_TYPES.HTTP)).toBe(DataType.JSON);
    });

    it("should return ANY for TRANSFORM node", () => {
      expect(getPrimaryOutputType(NODE_TYPES.TRANSFORM)).toBe(DataType.ANY);
    });

    it("should return ANY for BRANCH node (first output)", () => {
      expect(getPrimaryOutputType(NODE_TYPES.BRANCH)).toBe(DataType.ANY);
    });

    it("should return JSON for MERGE node", () => {
      expect(getPrimaryOutputType(NODE_TYPES.MERGE)).toBe(DataType.JSON);
    });

    it("should return VOID for OUTPUT node (no outputs)", () => {
      expect(getPrimaryOutputType(NODE_TYPES.OUTPUT)).toBe(DataType.VOID);
    });

    it("should return ANY for HUMAN_GATE node", () => {
      expect(getPrimaryOutputType(NODE_TYPES.HUMAN_GATE)).toBe(DataType.ANY);
    });

    it("should return ANY for MEMORY node", () => {
      expect(getPrimaryOutputType(NODE_TYPES.MEMORY)).toBe(DataType.ANY);
    });

    it("should return JSON for TOOL node", () => {
      expect(getPrimaryOutputType(NODE_TYPES.TOOL)).toBe(DataType.JSON);
    });

    it("should return JSON for SUBGRAPH node", () => {
      expect(getPrimaryOutputType(NODE_TYPES.SUBGRAPH)).toBe(DataType.JSON);
    });

    it("should return VOID for invalid node type", () => {
      expect(getPrimaryOutputType("invalid" as NodeType)).toBe(DataType.VOID);
    });
  });

  describe("getPrimaryInputType", () => {
    it("should return JSON for PROMPT node", () => {
      expect(getPrimaryInputType(NODE_TYPES.PROMPT)).toBe(DataType.JSON);
    });

    it("should return JSON for HTTP node (first input)", () => {
      expect(getPrimaryInputType(NODE_TYPES.HTTP)).toBe(DataType.JSON);
    });

    it("should return ANY for TRANSFORM node", () => {
      expect(getPrimaryInputType(NODE_TYPES.TRANSFORM)).toBe(DataType.ANY);
    });

    it("should return ANY for BRANCH node", () => {
      expect(getPrimaryInputType(NODE_TYPES.BRANCH)).toBe(DataType.ANY);
    });

    it("should return ANY for MERGE node", () => {
      expect(getPrimaryInputType(NODE_TYPES.MERGE)).toBe(DataType.ANY);
    });

    it("should return ANY for OUTPUT node", () => {
      expect(getPrimaryInputType(NODE_TYPES.OUTPUT)).toBe(DataType.ANY);
    });

    it("should return ANY for HUMAN_GATE node", () => {
      expect(getPrimaryInputType(NODE_TYPES.HUMAN_GATE)).toBe(DataType.ANY);
    });

    it("should return ANY for MEMORY node", () => {
      expect(getPrimaryInputType(NODE_TYPES.MEMORY)).toBe(DataType.ANY);
    });

    it("should return JSON for TOOL node", () => {
      expect(getPrimaryInputType(NODE_TYPES.TOOL)).toBe(DataType.JSON);
    });

    it("should return JSON for SUBGRAPH node", () => {
      expect(getPrimaryInputType(NODE_TYPES.SUBGRAPH)).toBe(DataType.JSON);
    });

    it("should return ANY for invalid node type", () => {
      expect(getPrimaryInputType("invalid" as NodeType)).toBe(DataType.ANY);
    });
  });

  describe("hasMultipleOutputs", () => {
    it("should return true for BRANCH node (has 2 outputs)", () => {
      expect(hasMultipleOutputs(NODE_TYPES.BRANCH)).toBe(true);
    });

    it("should return false for PROMPT node (has 1 output)", () => {
      expect(hasMultipleOutputs(NODE_TYPES.PROMPT)).toBe(false);
    });

    it("should return false for HTTP node (has 1 output)", () => {
      expect(hasMultipleOutputs(NODE_TYPES.HTTP)).toBe(false);
    });

    it("should return false for TRANSFORM node (has 1 output)", () => {
      expect(hasMultipleOutputs(NODE_TYPES.TRANSFORM)).toBe(false);
    });

    it("should return false for MERGE node (has 1 output)", () => {
      expect(hasMultipleOutputs(NODE_TYPES.MERGE)).toBe(false);
    });

    it("should return false for OUTPUT node (has 0 outputs)", () => {
      expect(hasMultipleOutputs(NODE_TYPES.OUTPUT)).toBe(false);
    });

    it("should return false for HUMAN_GATE node (has 1 output)", () => {
      expect(hasMultipleOutputs(NODE_TYPES.HUMAN_GATE)).toBe(false);
    });

    it("should return false for MEMORY node (has 1 output)", () => {
      expect(hasMultipleOutputs(NODE_TYPES.MEMORY)).toBe(false);
    });

    it("should return false for TOOL node (has 1 output)", () => {
      expect(hasMultipleOutputs(NODE_TYPES.TOOL)).toBe(false);
    });

    it("should return false for SUBGRAPH node (has 1 output)", () => {
      expect(hasMultipleOutputs(NODE_TYPES.SUBGRAPH)).toBe(false);
    });

    it("should return false for invalid node type", () => {
      expect(hasMultipleOutputs("invalid" as NodeType)).toBe(false);
    });
  });

  describe("acceptsMultipleInputs", () => {
    it("should return true for MERGE node (accepts multiple inputs)", () => {
      expect(acceptsMultipleInputs(NODE_TYPES.MERGE)).toBe(true);
    });

    it("should return false for PROMPT node", () => {
      expect(acceptsMultipleInputs(NODE_TYPES.PROMPT)).toBe(false);
    });

    it("should return false for HTTP node", () => {
      expect(acceptsMultipleInputs(NODE_TYPES.HTTP)).toBe(false);
    });

    it("should return false for TRANSFORM node", () => {
      expect(acceptsMultipleInputs(NODE_TYPES.TRANSFORM)).toBe(false);
    });

    it("should return false for BRANCH node", () => {
      expect(acceptsMultipleInputs(NODE_TYPES.BRANCH)).toBe(false);
    });

    it("should return false for OUTPUT node", () => {
      expect(acceptsMultipleInputs(NODE_TYPES.OUTPUT)).toBe(false);
    });

    it("should return false for HUMAN_GATE node", () => {
      expect(acceptsMultipleInputs(NODE_TYPES.HUMAN_GATE)).toBe(false);
    });

    it("should return false for MEMORY node", () => {
      expect(acceptsMultipleInputs(NODE_TYPES.MEMORY)).toBe(false);
    });

    it("should return false for TOOL node", () => {
      expect(acceptsMultipleInputs(NODE_TYPES.TOOL)).toBe(false);
    });

    it("should return false for SUBGRAPH node", () => {
      expect(acceptsMultipleInputs(NODE_TYPES.SUBGRAPH)).toBe(false);
    });

    it("should return false for invalid node type", () => {
      expect(acceptsMultipleInputs("invalid" as NodeType)).toBe(false);
    });
  });
});
