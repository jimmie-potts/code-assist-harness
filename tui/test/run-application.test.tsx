import {describe, expect, it, vi} from 'vitest';

import type {
  ApplicationRenderer,
  ApplicationTerminationSignal,
  ApplicationTerminationSubscriber,
} from '../src/run-application.js';
import {runApplication} from '../src/run-application.js';
import type {RuntimeState, RuntimeSupervisor} from '../src/runtime-supervisor.js';
import type {SessionUpdate} from '../src/session-state.js';

function createSupervisor(): RuntimeSupervisor & {
  readonly start: ReturnType<typeof vi.fn<() => Promise<void>>>;
  readonly stop: ReturnType<typeof vi.fn<() => Promise<void>>>;
  readonly submitTask: ReturnType<typeof vi.fn<(task: string) => string>>;
  readonly cancelSession: ReturnType<typeof vi.fn<() => boolean>>;
  readonly emitSessionUpdate: (update: SessionUpdate) => void;
} {
  let state: RuntimeState = {status: 'starting', workspace: '/workspace'};
  const listeners = new Set<(nextState: RuntimeState) => void>();
  const sessionListeners = new Set<(update: SessionUpdate) => void>();
  const start = vi.fn<() => Promise<void>>(async () => {
    state = {status: 'running', workspace: '/workspace'};
    for (const listener of listeners) {
      listener(state);
    }
  });
  const stop = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
  const submitTask = vi.fn<(task: string) => string>(() => 'cmd_test_001');
  const cancelSession = vi.fn<() => boolean>(() => true);

  return {
    getState: () => state,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    subscribeToSessionUpdates: (listener) => {
      sessionListeners.add(listener);
      return () => sessionListeners.delete(listener);
    },
    submitTask,
    cancelSession,
    emitSessionUpdate: (update) => {
      for (const listener of sessionListeners) {
        listener(update);
      }
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
    const root = renderApplication.mock.calls[0]?.[0];
    expect(root).toBeDefined();
    if (root !== undefined) {
      const properties = root.props as {readonly onCancelSession: () => boolean};
      expect(properties.onCancelSession()).toBe(true);
    }
    expect(supervisor.cancelSession).toHaveBeenCalledOnce();
    expect(rerender).toHaveBeenCalledOnce();
    expect(waitUntilExit).toHaveBeenCalledOnce();
    expect(supervisor.stop).toHaveBeenCalledOnce();
  });

  it('reduces ordered session updates before rerendering the terminal projection', async () => {
    const supervisor = createSupervisor();
    let resolveExit = (): void => undefined;
    const rerender = vi.fn();
    const renderApplication = vi.fn<ApplicationRenderer>(() => ({
      rerender,
      unmount: vi.fn(),
      waitUntilExit: () =>
        new Promise<void>((resolve) => {
          resolveExit = resolve;
        }),
    }));

    const running = runApplication(supervisor, renderApplication);
    await vi.waitFor(() => expect(supervisor.start).toHaveBeenCalledOnce());
    supervisor.emitSessionUpdate({
      type: 'task.submitted',
      commandId: 'cmd_stream_001',
      task: 'Explain streaming.',
    });
    supervisor.emitSessionUpdate({
      type: 'event.received',
      event: {
        protocol_version: 1,
        type: 'session.started',
        session_id: 'ses_stream_001',
        sequence: 1,
        timestamp: '2026-07-30T12:00:00.000Z',
        correlation_id: 'cmd_stream_001',
        payload: {},
      },
    });

    expect(rerender.mock.calls.at(-1)?.[0]).toMatchObject({
      props: {
        sessionState: {
          status: 'running',
          turns: [
            {
              task: 'Explain streaming.',
              sessionId: 'ses_stream_001',
              lastSequence: 1,
            },
          ],
        },
      },
    });

    resolveExit();
    await running;
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

  it('stops Python when Ink exits while runtime startup is still pending', async () => {
    const supervisor = createSupervisor();
    let resolveStartup = (): void => undefined;
    supervisor.start.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveStartup = resolve;
        }),
    );
    let resolveExit = (): void => undefined;
    const waitUntilExit = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveExit = resolve;
        }),
    );
    const renderApplication = vi.fn<ApplicationRenderer>(() => ({
      rerender: vi.fn(),
      unmount: vi.fn(),
      waitUntilExit,
    }));

    const running = runApplication(supervisor, renderApplication);
    await vi.waitFor(() => expect(waitUntilExit).toHaveBeenCalledOnce());
    resolveExit();
    await running;

    expect(supervisor.stop).toHaveBeenCalledOnce();
    resolveStartup();
  });

  it('preserves an Ink exit failure while runtime startup is still pending', async () => {
    const supervisor = createSupervisor();
    let resolveStartup = (): void => undefined;
    supervisor.start.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveStartup = resolve;
        }),
    );
    let rejectExit: ((error: Error) => void) | undefined;
    const waitUntilExit = vi.fn(
      () =>
        new Promise<void>((_resolve, reject) => {
          rejectExit = reject;
        }),
    );
    const renderApplication = vi.fn<ApplicationRenderer>(() => ({
      rerender: vi.fn(),
      unmount: vi.fn(),
      waitUntilExit,
    }));

    const running = runApplication(supervisor, renderApplication);
    await vi.waitFor(() => expect(waitUntilExit).toHaveBeenCalledOnce());
    rejectExit?.(new Error('Ink failed during startup'));

    await expect(running).rejects.toThrow('Ink failed during startup');
    expect(supervisor.stop).toHaveBeenCalledOnce();
    resolveStartup();
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
