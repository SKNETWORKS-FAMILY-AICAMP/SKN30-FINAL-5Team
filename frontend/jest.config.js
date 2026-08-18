module.exports = {
  preset: 'jest-expo',
  // `roots` is treated as a path, not a glob, so it survives a checkout
  // directory whose name contains glob-significant characters. Interpolating
  // <rootDir> into a testMatch pattern does not: on Windows the expansion keeps
  // backslashes, and a segment such as `\.worktrees` is read as an escaped dot
  // that then matches nothing.
  roots: ['<rootDir>/tests'],
  testMatch: ['**/*.test.ts', '**/*.test.tsx'],
  setupFilesAfterEnv: ['<rootDir>/tests/setup.ts'],
  collectCoverageFrom: ['src/**/*.{ts,tsx}', '!src/**/*.d.ts'],
};
