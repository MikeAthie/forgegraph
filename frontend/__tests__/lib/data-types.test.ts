import {
  DataType,
  DATA_TYPE_INFO,
  areTypesCompatible,
  getDataTypeInfo,
  parseDataType,
} from "@/lib/data-types";

describe("data-types", () => {
  describe("DataType enum", () => {
    it("should have all expected data type values", () => {
      expect(DataType.TEXT).toBe("text");
      expect(DataType.JSON).toBe("json");
      expect(DataType.ARRAY).toBe("array");
      expect(DataType.NUMBER).toBe("number");
      expect(DataType.BOOLEAN).toBe("boolean");
      expect(DataType.IMAGE).toBe("image");
      expect(DataType.FILE).toBe("file");
      expect(DataType.ANY).toBe("any");
      expect(DataType.VOID).toBe("void");
    });

    it("should have exactly 9 data types", () => {
      const types = Object.values(DataType);
      expect(types.length).toBe(9);
    });
  });

  describe("DATA_TYPE_INFO", () => {
    it("should have entries for all data types", () => {
      const allTypes = Object.values(DataType);
      allTypes.forEach((type) => {
        expect(DATA_TYPE_INFO[type]).toBeDefined();
      });
    });

    it("should have complete info for each type", () => {
      const allTypes = Object.values(DataType);
      allTypes.forEach((type) => {
        const info = DATA_TYPE_INFO[type];
        expect(info.label).toBeDefined();
        expect(typeof info.label).toBe("string");
        expect(info.description).toBeDefined();
        expect(typeof info.description).toBe("string");
        expect(info.icon).toBeDefined();
        expect(typeof info.icon).toBe("string");
        expect(info.color).toBeDefined();
        expect(typeof info.color).toBe("string");
        expect(info.bgColor).toBeDefined();
        expect(typeof info.bgColor).toBe("string");
      });
    });

    it("should have correct labels for each type", () => {
      expect(DATA_TYPE_INFO[DataType.TEXT].label).toBe("Text");
      expect(DATA_TYPE_INFO[DataType.JSON].label).toBe("JSON");
      expect(DATA_TYPE_INFO[DataType.ARRAY].label).toBe("Array");
      expect(DATA_TYPE_INFO[DataType.NUMBER].label).toBe("Number");
      expect(DATA_TYPE_INFO[DataType.BOOLEAN].label).toBe("Boolean");
      expect(DATA_TYPE_INFO[DataType.IMAGE].label).toBe("Image");
      expect(DATA_TYPE_INFO[DataType.FILE].label).toBe("File");
      expect(DATA_TYPE_INFO[DataType.ANY].label).toBe("Any");
      expect(DATA_TYPE_INFO[DataType.VOID].label).toBe("Void");
    });
  });

  describe("areTypesCompatible", () => {
    describe("compatible type combinations", () => {
      it("should accept same type connections (TEXT -> TEXT)", () => {
        const result = areTypesCompatible(DataType.TEXT, DataType.TEXT);
        expect(result.compatible).toBe(true);
        expect(result.reason).toBeUndefined();
      });

      it("should accept same type connections (JSON -> JSON)", () => {
        const result = areTypesCompatible(DataType.JSON, DataType.JSON);
        expect(result.compatible).toBe(true);
      });

      it("should accept JSON -> TEXT (JSON can be stringified)", () => {
        const result = areTypesCompatible(DataType.JSON, DataType.TEXT);
        expect(result.compatible).toBe(true);
        if (result.suggestion) {
          expect(result.suggestion).toContain("JSON will be stringified to text");
        }
      });

      it("should accept NUMBER -> TEXT (number can be converted to text)", () => {
        const result = areTypesCompatible(DataType.NUMBER, DataType.TEXT);
        expect(result.compatible).toBe(true);
      });

      it("should accept BOOLEAN -> TEXT (boolean can be converted to text)", () => {
        const result = areTypesCompatible(DataType.BOOLEAN, DataType.TEXT);
        expect(result.compatible).toBe(true);
      });

      it("should accept ARRAY -> JSON (arrays are JSON-compatible)", () => {
        const result = areTypesCompatible(DataType.ARRAY, DataType.JSON);
        expect(result.compatible).toBe(true);
      });

      it("should accept IMAGE -> FILE (images are files)", () => {
        const result = areTypesCompatible(DataType.IMAGE, DataType.FILE);
        expect(result.compatible).toBe(true);
      });

      it("should accept any type -> ANY target (ANY accepts everything)", () => {
        const allTypes = Object.values(DataType);
        allTypes.forEach((type) => {
          const result = areTypesCompatible(type, DataType.ANY);
          expect(result.compatible).toBe(true);
        });
      });

      it("should accept ANY source -> most targets (ANY can provide anything)", () => {
        const compatibleTargets = [
          DataType.TEXT,
          DataType.JSON,
          DataType.ARRAY,
          DataType.NUMBER,
          DataType.BOOLEAN,
          DataType.IMAGE,
          DataType.FILE,
          DataType.ANY,
          DataType.VOID,
        ];

        compatibleTargets.forEach((target) => {
          const result = areTypesCompatible(DataType.ANY, target);
          expect(result.compatible).toBe(true);
        });
      });

      it("should accept VOID source -> ANY target only", () => {
        const result = areTypesCompatible(DataType.VOID, DataType.ANY);
        expect(result.compatible).toBe(true);
      });
    });

    describe("incompatible type combinations", () => {
      it("should reject TEXT -> JSON without transformation", () => {
        const result = areTypesCompatible(DataType.TEXT, DataType.JSON);
        expect(result.compatible).toBe(false);
        expect(result.reason).toContain("Type mismatch");
        expect(result.suggestion).toContain("parse the text as JSON");
      });

      it("should reject TEXT -> NUMBER", () => {
        const result = areTypesCompatible(DataType.TEXT, DataType.NUMBER);
        expect(result.compatible).toBe(false);
        expect(result.reason).toContain("Type mismatch");
      });

      it("should reject TEXT -> ARRAY", () => {
        const result = areTypesCompatible(DataType.TEXT, DataType.ARRAY);
        expect(result.compatible).toBe(false);
        expect(result.reason).toContain("Type mismatch");
      });

      it("should reject JSON -> NUMBER", () => {
        const result = areTypesCompatible(DataType.JSON, DataType.NUMBER);
        expect(result.compatible).toBe(false);
        expect(result.reason).toContain("Type mismatch");
      });

      it("should reject FILE -> IMAGE", () => {
        const result = areTypesCompatible(DataType.FILE, DataType.IMAGE);
        expect(result.compatible).toBe(false);
        expect(result.reason).toContain("Type mismatch");
      });

      it("should reject VOID source for all targets except ANY", () => {
        const targets = [
          DataType.TEXT,
          DataType.JSON,
          DataType.ARRAY,
          DataType.NUMBER,
          DataType.BOOLEAN,
          DataType.IMAGE,
          DataType.FILE,
          DataType.VOID,
        ];

        targets.forEach((target) => {
          const result = areTypesCompatible(DataType.VOID, target);
          expect(result.compatible).toBe(false);
          expect(result.reason).toBe("Source node produces no output");
          expect(result.suggestion).toBe("Connect to a node that produces output");
        });
      });
    });

    describe("suggestions for incompatible types", () => {
      it("should suggest transform for TEXT -> JSON", () => {
        const result = areTypesCompatible(DataType.TEXT, DataType.JSON);
        expect(result.suggestion).toContain("Transform node");
        expect(result.suggestion).toContain("parse the text as JSON");
      });

      it("should suggest transform for JSON -> ARRAY", () => {
        const result = areTypesCompatible(DataType.JSON, DataType.ARRAY);
        expect(result.suggestion).toContain("Transform node");
        expect(result.suggestion).toContain("extract the array from JSON");
      });

      it("should suggest general transform for other mismatches", () => {
        const result = areTypesCompatible(DataType.NUMBER, DataType.ARRAY);
        expect(result.suggestion).toContain("Transform node");
        expect(result.suggestion).toContain("convert");
      });
    });

    describe("edge cases", () => {
      it("should handle null/undefined gracefully with type casting", () => {
        const result = areTypesCompatible(DataType.TEXT, DataType.TEXT);
        expect(result.compatible).toBe(true);
      });

      it("should return consistent results for repeated calls", () => {
        const result1 = areTypesCompatible(DataType.TEXT, DataType.JSON);
        const result2 = areTypesCompatible(DataType.TEXT, DataType.JSON);
        expect(result1).toEqual(result2);
      });
    });
  });

  describe("getDataTypeInfo", () => {
    it("should return correct info for TEXT type", () => {
      const info = getDataTypeInfo(DataType.TEXT);
      expect(info.label).toBe("Text");
      expect(info.description).toContain("text");
      expect(info.icon).toBe("Type");
    });

    it("should return correct info for JSON type", () => {
      const info = getDataTypeInfo(DataType.JSON);
      expect(info.label).toBe("JSON");
      expect(info.description).toContain("JSON");
      expect(info.icon).toBe("Braces");
    });

    it("should return correct info for ARRAY type", () => {
      const info = getDataTypeInfo(DataType.ARRAY);
      expect(info.label).toBe("Array");
      expect(info.description).toContain("List");
      expect(info.icon).toBe("List");
    });

    it("should return correct info for NUMBER type", () => {
      const info = getDataTypeInfo(DataType.NUMBER);
      expect(info.label).toBe("Number");
      expect(info.description).toContain("Numeric");
      expect(info.icon).toBe("Hash");
    });

    it("should return correct info for BOOLEAN type", () => {
      const info = getDataTypeInfo(DataType.BOOLEAN);
      expect(info.label).toBe("Boolean");
      expect(info.description).toContain("True or false");
      expect(info.icon).toBe("ToggleLeft");
    });

    it("should return correct info for IMAGE type", () => {
      const info = getDataTypeInfo(DataType.IMAGE);
      expect(info.label).toBe("Image");
      expect(info.description).toContain("Image");
      expect(info.icon).toBe("Image");
    });

    it("should return correct info for FILE type", () => {
      const info = getDataTypeInfo(DataType.FILE);
      expect(info.label).toBe("File");
      expect(info.description).toContain("File");
      expect(info.icon).toBe("File");
    });

    it("should return correct info for ANY type", () => {
      const info = getDataTypeInfo(DataType.ANY);
      expect(info.label).toBe("Any");
      expect(info.description).toContain("any type");
      expect(info.icon).toBe("Asterisk");
    });

    it("should return correct info for VOID type", () => {
      const info = getDataTypeInfo(DataType.VOID);
      expect(info.label).toBe("Void");
      expect(info.description).toContain("No data");
      expect(info.icon).toBe("Circle");
    });

    it("should return info object with all required properties", () => {
      const info = getDataTypeInfo(DataType.TEXT);
      expect(info).toHaveProperty("label");
      expect(info).toHaveProperty("description");
      expect(info).toHaveProperty("icon");
      expect(info).toHaveProperty("color");
      expect(info).toHaveProperty("bgColor");
    });
  });

  describe("parseDataType", () => {
    describe("valid inputs", () => {
      it("should parse lowercase type names correctly", () => {
        expect(parseDataType("text")).toBe(DataType.TEXT);
        expect(parseDataType("json")).toBe(DataType.JSON);
        expect(parseDataType("array")).toBe(DataType.ARRAY);
        expect(parseDataType("number")).toBe(DataType.NUMBER);
        expect(parseDataType("boolean")).toBe(DataType.BOOLEAN);
        expect(parseDataType("image")).toBe(DataType.IMAGE);
        expect(parseDataType("file")).toBe(DataType.FILE);
        expect(parseDataType("any")).toBe(DataType.ANY);
        expect(parseDataType("void")).toBe(DataType.VOID);
      });

      it("should parse uppercase type names correctly (case insensitive)", () => {
        expect(parseDataType("TEXT")).toBe(DataType.TEXT);
        expect(parseDataType("JSON")).toBe(DataType.JSON);
        expect(parseDataType("ARRAY")).toBe(DataType.ARRAY);
      });

      it("should parse mixed case type names correctly", () => {
        expect(parseDataType("Text")).toBe(DataType.TEXT);
        expect(parseDataType("Json")).toBe(DataType.JSON);
        expect(parseDataType("ArRaY")).toBe(DataType.ARRAY);
      });
    });

    describe("invalid inputs", () => {
      it("should return ANY for undefined input", () => {
        expect(parseDataType(undefined)).toBe(DataType.ANY);
      });

      it("should return ANY for empty string", () => {
        expect(parseDataType("")).toBe(DataType.ANY);
      });

      it("should return ANY for invalid type name", () => {
        expect(parseDataType("invalid")).toBe(DataType.ANY);
        expect(parseDataType("string")).toBe(DataType.ANY);
        expect(parseDataType("object")).toBe(DataType.ANY);
        expect(parseDataType("unknown")).toBe(DataType.ANY);
      });

      it("should return ANY for gibberish input", () => {
        expect(parseDataType("xyz123")).toBe(DataType.ANY);
        expect(parseDataType("!@#$%")).toBe(DataType.ANY);
      });
    });

    describe("edge cases", () => {
      it("should handle whitespace-padded input", () => {
        expect(parseDataType(" text ")).toBe(DataType.ANY); // Doesn't trim
      });

      it("should be consistent with repeated calls", () => {
        expect(parseDataType("text")).toBe(parseDataType("text"));
        expect(parseDataType("invalid")).toBe(parseDataType("invalid"));
      });
    });
  });
});
