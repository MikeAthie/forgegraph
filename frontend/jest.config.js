const path = require("path");
const nextJest = require("next/jest");

const createJestConfig = nextJest({
  // Provide the path to your Next.js app to load next.config.js and .env files in your test environment
  dir: "./",
});

// Add any custom config to be passed to Jest
const customJestConfig = {
  setupFilesAfterEnv: ["<rootDir>/jest.setup.js"],
  testEnvironment: "jest-environment-jsdom",
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/$1",
  },
  testMatch: ["**/__tests__/**/*.[jt]s?(x)", "**/?(*.)+(spec|test).[jt]s?(x)"],
  testPathIgnorePatterns: [
    "<rootDir>/__tests__/e2e/",
    "<rootDir>/__tests__/consulting/",
    "<rootDir>/__tests__/demo-captures/",
    "<rootDir>/__tests__/legacy-ultimate-test/",
    "<rootDir>/__tests__/.*/fixtures/",
  ],
  modulePathIgnorePatterns: ["<rootDir>/.next/"],
  cacheDirectory: process.env.JEST_CACHE_DIR || path.join(__dirname, ".jest-cache"),
  collectCoverageFrom: [
    "components/**/*.{js,jsx,ts,tsx}",
    "contexts/**/*.{js,jsx,ts,tsx}",
    "pages/**/*.{js,jsx,ts,tsx}",
    "lib/**/*.{js,jsx,ts,tsx}",
    "!**/*.d.ts",
    "!**/node_modules/**",
    "!**/.next/**",
    "!**/coverage/**",
  ],
  // Memory management - restart workers when they consume too much memory
  workerIdleMemoryLimit: "512MB",
  // Limit parallel workers to reduce memory pressure
  maxWorkers: "50%",
};

// createJestConfig is exported this way to ensure that next/jest can load the Next.js config which is async
module.exports = createJestConfig(customJestConfig);
