import { useCallback, useEffect, useReducer } from 'react';
import { ApiError, NetworkError } from '../api/client';

type Status = 'idle' | 'loading' | 'success' | 'error';

interface State<T> {
  status: Status;
  data: T | null;
  error: string | null;
}

type Action<T> =
  | { type: 'LOADING' }
  | { type: 'SUCCESS'; data: T }
  | { type: 'ERROR'; error: string }
  | { type: 'RESET' };

function reducer<T>(state: State<T>, action: Action<T>): State<T> {
  switch (action.type) {
    case 'LOADING': return { status: 'loading', data: null, error: null };
    case 'SUCCESS': return { status: 'success', data: action.data, error: null };
    case 'ERROR': return { status: 'error', data: null, error: action.error };
    case 'RESET': return { status: 'idle', data: null, error: null };
    default: return state;
  }
}

function extractMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof NetworkError) return err.message;
  if (err instanceof Error) return err.message;
  return 'An unexpected error occurred.';
}

/**
 * Generic async data fetching hook.
 * Returns { status, data, error, refetch }.
 */
export function useAsync<T>(
  fn: () => Promise<T>,
  deps: unknown[] = [],
): { status: Status; data: T | null; error: string | null; refetch: () => void } {
  const [state, dispatch] = useReducer(reducer<T>, {
    status: 'idle',
    data: null,
    error: null,
  });

  const execute = useCallback(() => {
    dispatch({ type: 'LOADING' });
    fn()
      .then((data) => dispatch({ type: 'SUCCESS', data }))
      .catch((err) => dispatch({ type: 'ERROR', error: extractMessage(err) }));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    execute();
  }, [execute]);

  return { ...state, refetch: execute };
}
