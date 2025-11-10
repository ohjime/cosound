import { atom } from 'jotai';

/**
 * Global auth state atoms
 */
export const userAtom = atom(null);
export const sessionAtom = atom(null);
export const authLoadingAtom = atom(true);

/**
 * Derived atom: Check if user is authenticated
 */
export const isAuthenticatedAtom = atom((get) => {
  const user = get(userAtom);
  const session = get(sessionAtom);
  return Boolean(user && session);
});
