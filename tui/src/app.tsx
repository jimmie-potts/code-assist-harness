import {useInput} from 'ink';
import {useEffect, useRef, useState, type ReactElement} from 'react';

import {MagicalMissionView} from './magical-mission.js';
import {SessionSubmissionError, type RuntimeState} from './runtime-supervisor.js';
import {
  isActiveSessionStatus,
  isCancellableSessionStatus,
} from './session-lifecycle.js';
import type {SessionState} from './session-state.js';

const WAIT_FOR_RUNTIME_FEEDBACK = 'Wait for the Python runtime to become ready.';
const WAIT_FOR_SESSION_FEEDBACK =
  'Wait for the active session to finish. Your input has been preserved.';

/** Runtime projection rendered by the terminal shell. */
export interface AppProperties {
  /** Current child lifecycle state; the component never decides or changes this state. */
  readonly runtimeState: RuntimeState;
  /** Current conversation projection reduced outside React from validated session updates. */
  readonly sessionState: SessionState;
  /** Submit exact non-empty user text through the supervised protocol owner. */
  readonly onSubmitTask: (task: string) => void;
  /** Request cancellation for the addressable active session; repeated requests are no-ops. */
  readonly onCancelSession: () => boolean;
}

/**
 * Render the conversation-first shell and its supervised Python runtime state.
 *
 * Ink owns the editable task buffer, Escape cancellation request, and Ctrl+C cleanup. Runtime and
 * session state are projections; the component neither reduces wire events nor decides a terminal
 * outcome. The callbacks cross into the supervised protocol owner only from eligible visible state.
 *
 * @param properties - Runtime/session projections and the supervised submission callback.
 * @returns The initial title, conversation, task-input, and status regions.
 */
export function App({
  runtimeState,
  sessionState,
  onSubmitTask,
  onCancelSession,
}: AppProperties): ReactElement {
  const [draft, setDraft] = useState('');
  const draftRef = useRef('');
  const [inputFeedback, setInputFeedback] = useState<string | undefined>();
  const updateDraft = (value: string): void => {
    draftRef.current = value;
    setDraft(value);
  };

  useEffect(() => {
    const runtimeBecameReady =
      inputFeedback === WAIT_FOR_RUNTIME_FEEDBACK && runtimeState.status === 'running';
    const sessionBecameAvailable =
      inputFeedback === WAIT_FOR_SESSION_FEEDBACK &&
      !isActiveProjection(sessionState);
    if (runtimeBecameReady || sessionBecameAvailable) {
      setInputFeedback(undefined);
    }
  }, [inputFeedback, runtimeState.status, sessionState.status]);

  useInput((input, key) => {
    if (key.escape) {
      if (
        runtimeState.status === 'running' &&
        sessionState.status !== 'protocol-failed' &&
        isCancellableSessionStatus(sessionState.status)
      ) {
        onCancelSession();
      }
      return;
    }
    if (key.return) {
      submitDraft(
        runtimeState,
        sessionState,
        draftRef.current,
        onSubmitTask,
        updateDraft,
        setInputFeedback,
      );
      return;
    }
    if (key.backspace || key.delete) {
      updateDraft(withoutLastCodePoint(draftRef.current));
      setInputFeedback(undefined);
      return;
    }
    if (key.ctrl || key.meta || key.tab) {
      return;
    }
    const printable = stripTerminalControls(input);
    if (printable.length > 0) {
      updateDraft(draftRef.current + printable);
      setInputFeedback(undefined);
    }
  });

  return (
    <MagicalMissionView
      canCancel={
        runtimeState.status === 'running' &&
        sessionState.status !== 'protocol-failed' &&
        isCancellableSessionStatus(sessionState.status)
      }
      draft={draft}
      inputFeedback={inputFeedback}
      runtimeState={runtimeState}
      sessionState={sessionState}
    />
  );
}

function stripTerminalControls(value: string): string {
  return [...value]
    .filter((character) => {
      const codePoint = character.codePointAt(0) ?? 0;
      return codePoint >= 32 && (codePoint < 127 || codePoint > 159);
    })
    .join('');
}

function withoutLastCodePoint(value: string): string {
  const codePoints = [...value];
  codePoints.pop();
  return codePoints.join('');
}

function submitDraft(
  runtimeState: RuntimeState,
  sessionState: SessionState,
  draft: string,
  onSubmitTask: (task: string) => void,
  setDraft: (value: string) => void,
  setInputFeedback: (value: string | undefined) => void,
): void {
  if (draft.trim().length === 0) {
    setInputFeedback('Enter a non-empty task before submitting.');
    return;
  }
  if (runtimeState.status !== 'running') {
    setInputFeedback(WAIT_FOR_RUNTIME_FEEDBACK);
    return;
  }
  if (isActiveProjection(sessionState)) {
    setInputFeedback(WAIT_FOR_SESSION_FEEDBACK);
    return;
  }
  if (sessionState.status === 'protocol-failed') {
    setInputFeedback('Restart after the session protocol failure before submitting another task.');
    return;
  }
  try {
    onSubmitTask(draft);
    setDraft('');
    setInputFeedback(undefined);
  } catch (error) {
    setInputFeedback(
      error instanceof SessionSubmissionError
        ? error.message
        : 'The task could not be submitted. Review the status and retry.',
    );
  }
}

function isActiveProjection(state: SessionState): boolean {
  return state.status !== 'protocol-failed' && isActiveSessionStatus(state.status);
}
