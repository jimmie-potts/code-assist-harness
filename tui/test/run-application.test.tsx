import {describe, expect, it, vi} from 'vitest';

import type {
  ApplicationRenderer,
  ApplicationTerminationSignal,
  ApplicationTerminationSubscriber,
} from '../src/run-application.js';
import {runApplication} from '../src/run-application.js';
import type {RuntimeState, RuntimeSupervisor} from '../src/runtime-supervisor.js';

function createSupervisor(): RuntimeSupervisor & {
  readonly start: ReturnType<typeof vi.fn<() => Promise<void>>>;
  readonly stop: ReturnType<typeof vi.fn<() => Promise<void>>>;
} {
  let state: RuntimeState = {status: 'starting', workspace: '/workspace'};
  const listeners = new Set<(nextState: RuntimeState) => void>();
  const start = vi.fn<() => Promise<void>>(async () => {
    state = {status: 'running', workspace: '/workspace'};
    for (const listener of listeners) {
      listener(state);
    }
  });
  const stop = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);

  return {
    getState: () => state,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    start,
    stop,
  };
}

describe('runApplication', () => {
  it('starts Python, projects transitions, and cleans up after Ink exits', async () => {
    const supervisor = createSupervisor();
    const rerender = vi.fn();
    const unmount = vi.fn();
    const waitUntilExit = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
    const renderApplication = vi.fn<ApplicationRenderer>(() => ({rerender, unmount, waitUntilExit}));

    await runApplication(supervisor, renderApplication);

    expect(renderApplication).toHaveBeenCalledOnce();
    expect(renderApplication.mock.calls[0]?.[1]).toEqual({exitOnCtrlC: true});
    expect(supervisor.start).toHaveBeenCalledOnce();
    expect(rerender).toHaveBeenCalledOnce();
    expect(waitUntilExit).toHaveBeenCalledOnce();
    expect(supervisor.stop).toHaveBeenCalledOnce();
  });

  it('stops Python when Ink exit rejects', async () => {
    const supervisor = createSupervisor();
    const waitUntilExit = vi.fn<() => Promise<void>>().mockRejectedValue(new Error('Ink failed'));
    const renderApplication = vi.fn<ApplicationRenderer>(() => ({
      rerender: vi.fn(),
      unmount: vi.fn(),
      waitUntilExit,
    }));

    await expect(runApplication(supervisor, renderApplication)).rejects.toThrow('Ink failed');

    expect(supervisor.stop).toHaveBeenCalledOnce();
  });

  it('keeps cleanup idempotent when rendering fails before spawn', async () => {
    const supervisor = createSupervisor();
    const renderApplication = vi.fn<ApplicationRenderer>(() => {
      throw new Error('render failed');
    });

    await expect(runApplication(supervisor, renderApplication)).rejects.toThrow('render failed');

    expect(supervisor.start).not.toHaveBeenCalled();
    expect(supervisor.stop).toHaveBeenCalledOnce();
  });

  it('routes SIGTERM through Ink unmount and the same child cleanup path', async () => {
    const supervisor = createSupervisor();
    let resolveExit = (): void => undefined;
    let didUnmount = false;
    const waitUntilExit = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          if (didUnmount) {
            resolve();
            return;
          }
          resolveExit = resolve;
        }),
    );
    const unmount = vi.fn(() => {
      didUnmount = true;
      resolveExit();
    });
    const renderApplication = vi.fn<ApplicationRenderer>(() => ({
      rerender: vi.fn(),
      unmount,
      waitUntilExit,
    }));
    let signalListener: ((signal: ApplicationTerminationSignal) => void) | undefined;
    const unsubscribe = vi.fn();
    const subscribeToTermination = vi.fn<ApplicationTerminationSubscriber>((listener) => {
      signalListener = listener;
      return unsubscribe;
    });

    const running = runApplication(supervisor, renderApplication, subscribeToTermination);
    expect(signalListener).toBeDefined();
    signalListener?.('SIGTERM');
    await running;

    expect(unmount).toHaveBeenCalledOnce();
    expect(unsubscribe).toHaveBeenCalledOnce();
    expect(supervisor.stop).toHaveBeenCalledOnce();
  });

  it('keeps process signal handlers installed until child cleanup settles', async () => {
    const supervisor = createSupervisor();
    let resolveStop = (): void => undefined;
    let markStopStarted = (): void => undefined;
    const stopStarted = new Promise<void>((resolve) => {
      markStopStarted = resolve;
    });
    supervisor.stop.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          markStopStarted();
          resolveStop = resolve;
        }),
    );

    let resolveExit = (): void => undefined;
    let didUnmount = false;
    const waitUntilExit = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          if (didUnmount) {
            resolve();
            return;
          }
          resolveExit = resolve;
        }),
    );
    const unmount = vi.fn(() => {
      didUnmount = true;
      resolveExit();
    });
    const renderApplication = vi.fn<ApplicationRenderer>(() => ({
      rerender: vi.fn(),
      unmount,
      waitUntilExit,
    }));
    const previousExitCode = process.exitCode;
    const on = vi.spyOn(process, 'on');
    const once = vi.spyOn(process, 'once');
    const removeListener = vi.spyOn(process, 'removeListener');
    let signalHandler: (() => void) | undefined;

    try {
      const running = runApplication(supervisor, renderApplication);
      signalHandler = on.mock.calls.find(([event]) => event === 'SIGTERM')?.[1] as
        | (() => void)
        | undefined;
      expect(signalHandler).toBeDefined();
      expect(once).not.toHaveBeenCalledWith('SIGTERM', expect.any(Function));

      signalHandler?.();
      await stopStarted;
      expect(removeListener).not.toHaveBeenCalledWith('SIGTERM', signalHandler);

      signalHandler?.();
      expect(unmount).toHaveBeenCalledOnce();
      expect(process.exitCode).toBe(143);

      resolveStop();
      await running;

      expect(removeListener).toHaveBeenCalledWith('SIGTERM', signalHandler);
      expect(supervisor.stop).toHaveBeenCalledOnce();
    } finally {
      if (signalHandler !== undefined) {
        process.removeListener('SIGTERM', signalHandler);
      }
      process.exitCode = previousExitCode;
      on.mockRestore();
      once.mockRestore();
      removeListener.mockRestore();
    }
  });
});
