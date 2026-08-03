import {render} from 'ink-testing-library';
import {describe, expect, it, vi} from 'vitest';

import {App} from '../src/app.js';
import {
  MagicalMissionView,
  projectFamiliar,
  resolveMissionPresentation,
} from '../src/magical-mission.js';
import type {RuntimeState} from '../src/runtime-supervisor.js';
import {
  INITIAL_SESSION_STATE,
  reduceSessionState,
  type SessionEvent,
  type SessionState,
} from '../src/session-state.js';

const TIMESTAMP = '2026-08-02T12:00:00.000Z';
const COMMAND_ID = 'cmd_magical_001';
const SESSION_ID = 'ses_magical_001';
const RUNNING_RUNTIME: RuntimeState = {status: 'running', workspace: '/workspace'};

const SESSION_FAMILIARS = {
  idle: {
    face: '૮ ˶ᵔ ᵕ ᵔ˶ ა',
    callout: 'READY FOR A MISSION!',
    compactStatus: 'READY',
    color: '#58d68d',
  },
  starting: {
    face: '૮ ˶• ᴗ •˶ ა',
    callout: 'SUMMONING THE MISSION…',
    compactStatus: 'SUMMONING',
    color: '#59d6ff',
  },
  running: {
    face: '٩(ˊᗜˋ*)و',
    callout: 'POWERING UP!',
    compactStatus: 'RUNNING',
    color: '#ff5da2',
  },
  awaiting_approval: {
    face: '(๑•̀ᗝ•́)૭',
    callout: 'ACTION REQUIRED',
    compactStatus: 'ACTION REQUIRED',
    color: '#ffd166',
  },
  cancelling: {
    face: '૮ ˶• ﻌ •˶ ა',
    callout: 'CANCELLATION REQUESTED · WAITING FOR PYTHON',
    compactStatus: 'CANCELLING',
    color: '#ffd166',
  },
  completed: {
    face: 'ヽ(>∀<☆)ノ',
    callout: 'MISSION COMPLETE!',
    compactStatus: 'COMPLETE',
    color: '#58d68d',
  },
  cancelled: {
    face: '૮ ˶ᵔ ﻌ ᵔ˶ ა',
    callout: 'MISSION CANCELLED',
    compactStatus: 'CANCELLED',
    color: '#ffd166',
  },
  failed: {
    face: '(｡•́︿•̀｡)',
    callout: 'MISSION FAILED',
    compactStatus: 'FAILED',
    color: '#ff667d',
  },
  'protocol-failed': {
    face: '(⊙﹏⊙)',
    callout: 'PROTOCOL FAILED · RESTART REQUIRED',
    compactStatus: 'PROTOCOL FAILED',
    color: '#ff667d',
  },
} as const satisfies Readonly<
  Record<SessionState['status'], ReturnType<typeof projectFamiliar>>
>;

const RUNTIME_FAMILIARS = {
  starting: {
    runtimeState: {status: 'starting', workspace: '/workspace'},
    expected: {
      face: '૮ ˶• ﻌ •˶ ა',
      callout: 'PYTHON IS WAKING UP…',
      compactStatus: 'WAKING',
      color: '#59d6ff',
    },
  },
  running: {
    runtimeState: RUNNING_RUNTIME,
    expected: SESSION_FAMILIARS.awaiting_approval,
  },
  'failed-to-start': {
    runtimeState: {
      status: 'failed-to-start',
      workspace: '/workspace',
      message: 'Python could not start.',
    },
    expected: {
      face: '૮ ˶× ﻌ ×˶ ა',
      callout: 'RUNTIME FAILED TO START',
      compactStatus: 'RUNTIME FAILED',
      color: '#ff667d',
    },
  },
  'protocol-failed': {
    runtimeState: {
      status: 'protocol-failed',
      workspace: '/workspace',
      code: 'unknown_type',
      message: 'Protocol input was rejected.',
    },
    expected: {
      face: '૮ ˶⊙ ﻌ ⊙˶ ა',
      callout: 'RUNTIME PROTOCOL FAILED',
      compactStatus: 'PROTOCOL FAILED',
      color: '#ff667d',
    },
  },
  'unexpectedly-exited': {
    runtimeState: {
      status: 'unexpectedly-exited',
      workspace: '/workspace',
      message: 'Python exited unexpectedly.',
    },
    expected: {
      face: '(⊙﹏⊙)',
      callout: 'RUNTIME EXITED UNEXPECTEDLY',
      compactStatus: 'RUNTIME EXITED',
      color: '#ff667d',
    },
  },
  stopping: {
    runtimeState: {status: 'stopping', workspace: '/workspace'},
    expected: {
      face: '૮ ˶- ﻌ -˶ ა',
      callout: 'RUNTIME STOPPING…',
      compactStatus: 'STOPPING',
      color: '#ffd166',
    },
  },
  stopped: {
    runtimeState: {status: 'stopped', workspace: '/workspace'},
    expected: {
      face: '૮ ˶ᵕ ﻌ ᵕ˶ ა',
      callout: 'RUNTIME STOPPED',
      compactStatus: 'STOPPED',
      color: '#c79bff',
    },
  },
} as const satisfies Readonly<
  Record<
    RuntimeState['status'],
    {readonly runtimeState: RuntimeState; readonly expected: ReturnType<typeof projectFamiliar>}
  >
>;

describe('resolveMissionPresentation', () => {
  it('selects the exact wide, stacked, and compact column boundaries', () => {
    expect(resolveMissionPresentation(96, 24)).toMatchObject({layout: 'wide', roomy: true});
    expect(resolveMissionPresentation(95, 24)).toMatchObject({layout: 'stacked', roomy: true});
    expect(resolveMissionPresentation(56, 23)).toMatchObject({layout: 'stacked', roomy: false});
    expect(resolveMissionPresentation(55, 23)).toMatchObject({layout: 'compact', roomy: false});
  });

  it('degrades familiar, emoji, and border choices at their exact size thresholds', () => {
    expect(resolveMissionPresentation(48, 18)).toMatchObject({
      showFamiliar: true,
      showEmoji: true,
      panelBorder: 'round',
    });
    expect(resolveMissionPresentation(47, 18)).toMatchObject({
      showFamiliar: true,
      showEmoji: false,
      panelBorder: 'round',
    });
    expect(resolveMissionPresentation(39, 18)).toMatchObject({showFamiliar: false});
    expect(resolveMissionPresentation(40, 17)).toMatchObject({showFamiliar: false});
    expect(resolveMissionPresentation(31, 24)).toMatchObject({panelBorder: 'classic'});
  });

  it('honors explicit no-color and dumb-terminal capability choices', () => {
    expect(resolveMissionPresentation(110, 30, {noColor: ''})).toMatchObject({
      colorEnabled: false,
      layout: 'wide',
      panelBorder: 'round',
      showEmoji: true,
      showFamiliar: true,
    });
    expect(resolveMissionPresentation(110, 30, {term: 'dumb'})).toMatchObject({
      colorEnabled: false,
      layout: 'wide',
      panelBorder: 'classic',
      showEmoji: false,
      showFamiliar: false,
    });
  });
});

describe('projectFamiliar', () => {
  it.each(Object.entries(SESSION_FAMILIARS))(
    'projects the complete $0 session expression while Python is running',
    (status, expected) => {
      expect(
        projectFamiliar(RUNNING_RUNTIME, {
          ...INITIAL_SESSION_STATE,
          status: status as SessionState['status'],
        }),
      ).toEqual(expected);
    },
  );

  it.each(Object.entries(RUNTIME_FAMILIARS))(
    'projects the complete $0 runtime expression with documented precedence',
    (_status, {runtimeState, expected}) => {
      expect(
        projectFamiliar(runtimeState, {
          ...INITIAL_SESSION_STATE,
          status: 'awaiting_approval',
        }),
      ).toEqual(expected);
    },
  );
});

describe('MagicalMissionView', () => {
  it('renders wide, stacked, and compact layouts without losing semantic regions or the draft', async () => {
    const state = runningSession('Review the provider boundary.');
    const view = renderMission({
      draft: 'Preserve this next mission',
      sessionState: state,
      canCancel: true,
    });

    try {
      await resizeTerminal(view, 110, 30);
      const wide = requiredFrame(view);
      expect(wide).toContain('Code Assist Harness // STAR COMMAND');
      expect(wide).toContain('MISSION LOG · Conversation');
      expect(wide).toContain('YOUR FAMILIAR');
      expect(wide).toContain('POWERING UP!');
      expect(wide).toContain('NEXT COMMAND · Task input · draft preserved while mission runs');
      expect(wide).toContain('Preserve this next mission');
      expect(wide).toContain('Session status: running · streaming response · Esc to cancel');
      expect(wide).toContain('Status: runtime running');
      expect(sectionLine(wide, 'MISSION LOG · Conversation')).toContain('YOUR FAMILIAR');

      await resizeTerminal(view, 110, 23);
      const nonRoomyWide = requiredFrame(view);
      expect(nonRoomyWide).toContain('FAMILIAR · ٩(ˊᗜˋ*)و · RUNNING');
      expect(nonRoomyWide).not.toContain('YOUR FAMILIAR');
      expect(nonRoomyWide).not.toContain('POWERING UP!');
      expect(sectionLine(nonRoomyWide, 'MISSION LOG · Conversation')).not.toContain(
        'FAMILIAR ·',
      );
      expect(nonRoomyWide).toContain('Session status: running');
      expect(nonRoomyWide).toContain('Status: runtime running');

      await resizeTerminal(view, 76, 24);
      const stacked = requiredFrame(view);
      expect(stacked).toContain('MISSION LOG · Conversation');
      expect(stacked).toContain('YOUR FAMILIAR ·');
      expect(stacked).toContain('Preserve this next mission');
      expect(sectionIndex(stacked, 'MISSION LOG · Conversation')).toBeLessThan(
        sectionIndex(stacked, 'YOUR FAMILIAR ·'),
      );
      expect(sectionLine(stacked, 'MISSION LOG · Conversation')).not.toContain('YOUR FAMILIAR');

      await resizeTerminal(view, 44, 20);
      const compact = requiredFrame(view);
      expect(compact).toContain('Code Assist Harness');
      expect(compact).toContain('STAR COMMAND');
      expect(compact).toContain('MISSION LOG · Conversation');
      expect(compact).not.toContain('YOUR FAMILIAR');
      expect(compact).toContain('٩(ˊᗜˋ*)و · RUNNING');
      expect(compact).toContain('Preserve this next mission');
      expect(compact).toContain('Session status: running');
      expect(compact).toContain('Esc to cancel');
      expect(compact).toContain('Ctrl+C to exit');
    } finally {
      view.unmount();
    }
  });

  it('preserves the App-owned pending draft without callbacks across a real Ink resize', async () => {
    const onSubmitTask = vi.fn();
    const onCancelSession = vi.fn(() => false);
    const view = render(
      <App
        onCancelSession={onCancelSession}
        onSubmitTask={onSubmitTask}
        runtimeState={RUNNING_RUNTIME}
        sessionState={INITIAL_SESSION_STATE}
      />,
    );

    try {
      view.stdin.write('Preserve this App-owned mission');
      await vi.waitFor(() =>
        expect(requiredFrame(view)).toContain('Preserve this App-owned mission'),
      );

      for (const [columns, rows] of [
        [110, 30],
        [76, 24],
        [44, 20],
      ] as const) {
        await resizeTerminal(view, columns, rows);
        expect(requiredFrame(view)).toContain('Preserve this App-owned mission');
      }

      expect(onSubmitTask).not.toHaveBeenCalled();
      expect(onCancelSession).not.toHaveBeenCalled();
    } finally {
      view.unmount();
    }
  });

  it('celebrates a healthy wide projection when emoji are available', async () => {
    const view = renderMission();

    try {
      await resizeTerminal(view, 110, 30);
      expect(requiredFrame(view)).toContain('MISSION: IDLE · POWER: READY 💖');
    } finally {
      view.unmount();
    }
  });

  it.each([
    {
      name: 'runtime warning',
      runtimeState: {
        ...RUNNING_RUNTIME,
        warning: {code: 'invalid_task', message: 'The task was rejected safely.'},
      },
      sessionState: INITIAL_SESSION_STATE,
    },
    {
      name: 'recording warning',
      runtimeState: {
        ...RUNNING_RUNTIME,
        recordingWarning: {
          code: 'transcript_persistence_failed',
          message: 'Recording is unavailable but work may continue.',
        },
      },
      sessionState: INITIAL_SESSION_STATE,
    },
    {
      name: 'session startup',
      runtimeState: RUNNING_RUNTIME,
      sessionState: submittedSession('Start this mission.'),
    },
    {
      name: 'approval',
      runtimeState: RUNNING_RUNTIME,
      sessionState: awaitingApprovalSession(),
    },
    {
      name: 'cancellation',
      runtimeState: RUNNING_RUNTIME,
      sessionState: cancellingSession(),
    },
    {
      name: 'cancelled session',
      runtimeState: RUNNING_RUNTIME,
      sessionState: cancelledSession(),
    },
    {
      name: 'session failure',
      runtimeState: RUNNING_RUNTIME,
      sessionState: failedSession('Approval could not be completed safely.'),
    },
    {
      name: 'session protocol failure',
      runtimeState: RUNNING_RUNTIME,
      sessionState: protocolFailedSession(),
    },
  ] as const)(
    'suppresses celebration for $name in a wide emoji-capable projection',
    async ({runtimeState, sessionState}) => {
      const view = renderMission({runtimeState, sessionState});

      try {
        await resizeTerminal(view, 110, 30);
        const frame = requiredFrame(view);
        expect(frame).toContain('POWER: READY');
        expect(frame).not.toContain('💖');
      } finally {
        view.unmount();
      }
    },
  );

  it.each([
    {
      name: 'unavailable runtime',
      runtimeState: {status: 'starting', workspace: '/workspace'},
      sessionState: INITIAL_SESSION_STATE,
      heading: 'TASK DRAFT · Task input · waiting for runtime',
    },
    {
      name: 'session protocol failure',
      runtimeState: RUNNING_RUNTIME,
      sessionState: protocolFailedSession(),
      heading: 'TASK DRAFT · Task input · restart required before submission',
    },
  ] as const)(
    'states input availability truthfully for an $name',
    async ({runtimeState, sessionState, heading}) => {
      const view = renderMission({
        draft: 'Keep this draft visible',
        runtimeState,
        sessionState,
      });

      try {
        await resizeTerminal(view, 110, 30);
        const frame = requiredFrame(view);
        expect(frame).toContain(heading);
        expect(frame).toContain('Keep this draft visible');
      } finally {
        view.unmount();
      }
    },
  );

  it.each([
    {
      name: 'starting runtime',
      runtimeState: {status: 'starting', workspace: '/workspace'},
      power: 'WAKING',
    },
    {
      name: 'failed startup',
      runtimeState: {
        status: 'failed-to-start',
        workspace: '/workspace',
        message: 'Python could not start.',
      },
      power: 'ALERT',
    },
    {
      name: 'runtime protocol failure',
      runtimeState: {
        status: 'protocol-failed',
        workspace: '/workspace',
        code: 'unknown_type',
        message: 'Protocol input was rejected.',
      },
      power: 'ALERT',
    },
    {
      name: 'unexpected runtime exit',
      runtimeState: {
        status: 'unexpectedly-exited',
        workspace: '/workspace',
        message: 'Python exited unexpectedly.',
      },
      power: 'ALERT',
    },
    {
      name: 'stopping runtime',
      runtimeState: {status: 'stopping', workspace: '/workspace'},
      power: 'STOPPING',
    },
    {
      name: 'stopped runtime',
      runtimeState: {status: 'stopped', workspace: '/workspace'},
      power: 'OFFLINE',
    },
  ] as const)(
    'renders $power for a $name in the wide header',
    async ({runtimeState, power}) => {
      const view = renderMission({runtimeState});

      try {
        await resizeTerminal(view, 110, 30);
        const frame = requiredFrame(view);
        expect(frame).toContain(`POWER: ${power}`);
        expect(frame).not.toContain('💖');
      } finally {
        view.unmount();
      }
    },
  );

  it('keeps the idle emergency projection within a 30 by 16 terminal', async () => {
    const view = renderMission();

    try {
      await resizeTerminal(view, 30, 16);
      const frame = requiredFrame(view);
      expect(frame.split('\n').length).toBeLessThanOrEqual(16);
      expect(frame).toContain('Code Assist Harness');
      expect(frame).toContain('Conversation');
      expect(frame).toContain('Task input');
      expect(frame).toContain('Session status: idle');
      expect(frame).toContain('Status: runtime running');
      expect(frame).toContain('workspace: /workspace');
      expect(frame).toContain('Ctrl+C to exit');
      expect(frame).not.toContain('YOUR FAMILIAR');
      expect(frame).not.toContain('✨');
    } finally {
      view.unmount();
    }
  });

  it('keeps complete warning and failure evidence in the compact projection', async () => {
    const warningTail = 'WARNING-END';
    const warningRuntime: RuntimeState = {
      status: 'running',
      workspace: '/workspace',
      warning: {
        code: 'invalid_task',
        message: `The submitted task was rejected safely. ${warningTail}`,
      },
      recordingWarning: {
        code: 'transcript_persistence_failed',
        message: 'Recording is unavailable but work may continue. RECORDING-END',
      },
    };
    const approvalState = awaitingApprovalSession();
    const warningView = renderMission({
      runtimeState: warningRuntime,
      sessionState: approvalState,
      canCancel: true,
    });

    try {
      await resizeTerminal(warningView, 44, 20);
      const frame = requiredFrame(warningView);
      const normalized = normalizedFrame(frame);
      expect(normalized).toContain('WARNING · Runtime warning (invalid_task)');
      expect(normalized).toContain(warningTail);
      expect(normalized).toContain(
        'WARNING · Recording warning (transcript_persistence_failed)',
      );
      expect(normalized).toContain('RECORDING-END');
      expect(normalized).toContain('ACTION REQUIRED');
      expect(normalized).not.toContain('💖');
      expect(normalized).toContain('Session status: awaiting approval');
      expect(sectionIndex(frame, 'WARNING · Runtime warning')).toBeLessThan(
        sectionIndex(frame, 'MISSION LOG · Conversation'),
      );
    } finally {
      warningView.unmount();
    }

    const failureMessage = 'Approval could not be completed safely. FAILURE-END';
    const failureView = renderMission({sessionState: failedSession(failureMessage)});
    try {
      await resizeTerminal(failureView, 44, 20);
      const frame = normalizedFrame(requiredFrame(failureView));
      expect(frame).toContain('(｡•́︿•̀｡) · FAILED');
      expect(frame).toContain(
        'ERROR · Session failed (approval.unavailable): Approval could not be completed safely.',
      );
      expect(frame).toContain('Session status: failed (approval.unavailable)');
      expect(frame).toContain(failureMessage);
      expect(frame).toContain('ready for another task');
      expect(frame).not.toContain('💖');
    } finally {
      failureView.unmount();
    }

    const runtimeFailureView = renderMission({
      runtimeState: {
        status: 'protocol-failed',
        workspace: '/workspace',
        code: 'unknown_type',
        message: 'Protocol input was rejected. RUNTIME-END',
      },
    });
    try {
      await resizeTerminal(runtimeFailureView, 44, 20);
      const rawFrame = requiredFrame(runtimeFailureView);
      const frame = normalizedFrame(rawFrame);
      expect(frame).toContain(
        'ERROR · Runtime protocol failed (unknown_type): Protocol input was rejected. RUNTIME-END',
      );
      expect(sectionIndex(rawFrame, 'ERROR · Runtime protocol failed')).toBeLessThan(
        sectionIndex(rawFrame, 'MISSION LOG · Conversation'),
      );
      expect(frame).toContain('Status: runtime protocol failed (unknown_type)');
      expect(frame).toContain('Ctrl+C to exit');
      expect(frame).not.toContain('💖');
    } finally {
      runtimeFailureView.unmount();
    }
  });

  it('renders no-color semantics unchanged and a dumb terminal with reduced decoration', async () => {
    const state = runningSession('Keep the mission readable.');
    const noColorView = renderMission({
      sessionState: state,
      canCancel: true,
      terminalEnvironment: {noColor: '1', term: 'xterm-256color'},
    });

    try {
      await resizeTerminal(noColorView, 76, 24);
      const frame = requiredFrame(noColorView);
      expect(frame).toContain('Code Assist Harness');
      expect(frame).toContain('POWERING UP!');
      expect(frame).toContain('Session status: running');
      expect(frame).toContain('Status: runtime running');
    } finally {
      noColorView.unmount();
    }

    const dumbView = renderMission({
      sessionState: state,
      canCancel: true,
      terminalEnvironment: {term: 'dumb'},
    });
    try {
      await resizeTerminal(dumbView, 76, 24);
      const frame = requiredFrame(dumbView);
      expect(frame).not.toContain('YOUR FAMILIAR');
      expect(frame).not.toContain('🍓');
      expect(frame).not.toContain('🐣');
      expect(frame).not.toContain('✨');
      expect(frame).toContain('Conversation');
      expect(frame).toContain('Task input');
      expect(frame).toContain('Session status: running');
      expect(frame).toContain('Status: runtime running');
    } finally {
      dumbView.unmount();
    }
  });
});

type RenderedMission = ReturnType<typeof render>;

function renderMission({
  runtimeState = RUNNING_RUNTIME,
  sessionState = INITIAL_SESSION_STATE,
  draft = '',
  canCancel = false,
  terminalEnvironment = {term: 'xterm-256color'},
}: {
  readonly runtimeState?: RuntimeState;
  readonly sessionState?: SessionState;
  readonly draft?: string;
  readonly canCancel?: boolean;
  readonly terminalEnvironment?: {readonly noColor?: string; readonly term?: string};
} = {}): RenderedMission {
  return render(
    <MagicalMissionView
      canCancel={canCancel}
      draft={draft}
      runtimeState={runtimeState}
      sessionState={sessionState}
      terminalEnvironment={terminalEnvironment}
    />,
  );
}

async function resizeTerminal(
  view: RenderedMission,
  columns: number,
  rows: number,
): Promise<void> {
  const priorFrameCount = view.frames.length;
  Object.defineProperties(view.stdout, {
    columns: {configurable: true, value: columns},
    rows: {configurable: true, value: rows},
  });
  view.stdout.emit('resize');
  await vi.waitFor(() => expect(view.frames.length).toBeGreaterThan(priorFrameCount));
}

function requiredFrame(view: RenderedMission): string {
  const frame = view.lastFrame();
  if (frame === undefined) {
    throw new Error('Ink did not render a frame.');
  }
  return frame;
}

function sectionLine(frame: string, label: string): string {
  const line = frame.split('\n').find((candidate) => candidate.includes(label));
  if (line === undefined) {
    throw new Error(`Rendered frame did not contain section: ${label}`);
  }
  return line;
}

function sectionIndex(frame: string, label: string): number {
  const index = frame.indexOf(label);
  if (index < 0) {
    throw new Error(`Rendered frame did not contain section: ${label}`);
  }
  return index;
}

function normalizedFrame(frame: string): string {
  return frame.replace(/[\u2500-\u257f]/gu, ' ').replace(/\s+/g, ' ').trim();
}

function runningSession(task: string): SessionState {
  return receive(submittedSession(task), 'session.started', 1, {});
}

function awaitingApprovalSession(): SessionState {
  return reduceSessionState(runningSession('Review this mission.'), {
    type: 'approval.requested',
    sessionId: SESSION_ID,
  });
}

function cancellingSession(): SessionState {
  return reduceSessionState(runningSession('Cancel this mission.'), {
    type: 'cancel.requested',
    commandId: 'cmd_cancel_001',
    sessionId: SESSION_ID,
  });
}

function cancelledSession(): SessionState {
  return reduceSessionState(cancellingSession(), {
    type: 'event.received',
    event: {
      protocol_version: 1,
      type: 'session.cancelled',
      session_id: SESSION_ID,
      sequence: 2,
      timestamp: TIMESTAMP,
      correlation_id: 'cmd_cancel_001',
      payload: {},
    },
  });
}

function protocolFailedSession(): SessionState {
  return reduceSessionState(runningSession('Keep protocol truth visible.'), {
    type: 'task.submitted',
    commandId: 'cmd_illegal_overlap',
    task: 'This overlap must fail closed.',
  });
}

function failedSession(message: string): SessionState {
  return receive(runningSession('Approve this mission.'), 'session.failed', 2, {
    code: 'approval.unavailable',
    message,
  });
}

function submittedSession(task: string): SessionState {
  return reduceSessionState(INITIAL_SESSION_STATE, {
    type: 'task.submitted',
    commandId: COMMAND_ID,
    task,
  });
}

function receive(
  state: SessionState,
  type: 'session.started' | 'session.failed',
  sequence: number,
  payload: Record<string, string>,
): SessionState {
  return reduceSessionState(state, {
    type: 'event.received',
    event: {
      protocol_version: 1,
      type,
      session_id: SESSION_ID,
      sequence,
      timestamp: TIMESTAMP,
      correlation_id: COMMAND_ID,
      payload,
    } as SessionEvent,
  });
}
