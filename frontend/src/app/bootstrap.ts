export type BootDestination = 'Auth' | 'Main';

export type BootDestinationResolver = () => Promise<BootDestination>;

/**
 * Authentication restoration will be connected through this boundary.
 * The migration slice intentionally reads no token, identifier, or health data.
 */
export const resolveBootDestination: BootDestinationResolver = async () =>
  'Auth';
