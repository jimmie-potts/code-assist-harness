import {Box, Text, useInput} from 'ink';
import {useEffect, useRef, useState, type ReactElement} from 'react';

import {SessionSubmissionError, type RuntimeState} from './runtime-supervisor.js';
import type {ConversationTurn, SessionState} from './session-state.js';

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
      sessionState.status !== 'starting' &&
      sessionState.status !== 'running' &&
      sessionState.status !== 'cancelling';
    if (runtimeBecameReady || sessionBecameAvailable) {
      setInputFeedback(undefined);
    }
  }, [inputFeedback, runtimeState.status, sessionState.status]);

  useInput((input, key) => {
    if (key.escape) {
      if (runtimeState.status === 'running' && sessionState.status === 'running') {
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
    <Box flexDirection="column" paddingX={1}>
      <Text bold color="cyan">
        Code Assist Harness
      </Text>

      <Box flexDirection="column" marginTop={1}>
        <Text bold>Conversation</Text>
        <Box borderStyle="round" flexDirection="column" paddingX={1}>
          <Conversation turns={sessionState.turns} />
        </Box>
      </Box>

      <Box flexDirection="column" marginTop={1}>
        <Text bold>Task input</Text>
        <Box borderStyle="round" paddingX={1}>
          <Text>&gt; </Text>
          {draft.length === 0 ? (
            <Text dimColor>Type a task and press Enter</Text>
          ) : (
            <Text>{draft}</Text>
          )}
        </Box>
        {inputFeedback === undefined ? null : <Text color="yellow">{inputFeedback}</Text>}
      </Box>

      <Box marginTop={1}>
        <SessionStatus
          state={sessionState}
          canCancel={runtimeState.status === 'running' && sessionState.status === 'running'}
        />
      </Box>

      <Box>
        <RuntimeStatus state={runtimeState} />
      </Box>
    </Box>
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

function Conversation({turns}: {readonly turns: readonly ConversationTurn[]}): ReactElement {
  if (turns.length === 0) {
    return <Text dimColor>No messages yet.</Text>;
  }
  return (
    <>
      {turns.map((turn) => (
        <Box key={turn.commandId} flexDirection="column" marginBottom={1}>
          <Text>
            <Text bold color="cyan">
              You:
            </Text>{' '}
            {turn.task}
          </Text>
          <Text>
            <Text bold color="green">
              Assistant:
            </Text>{' '}
            {assistantText(turn)}
          </Text>
        </Box>
      ))}
    </>
  );
}

function assistantText(turn: ConversationTurn): ReactElement | string {
  if (turn.assistantText.length > 0) {
    return turn.assistantText;
  }
  switch (turn.status) {
    case 'starting':
      return <Text dimColor>Starting…</Text>;
    case 'running':
      return <Text dimColor>Waiting for response…</Text>;
    case 'cancelling':
      return <Text dimColor>Cancelling…</Text>;
    case 'cancelled':
      return <Text dimColor>Cancelled before a response.</Text>;
    case 'completed':
      return <Text dimColor>No response text.</Text>;
  }
}

function SessionStatus({
  state,
  canCancel,
}: {
  readonly state: SessionState;
  readonly canCancel: boolean;
}): ReactElement {
  switch (state.status) {
    case 'idle':
      return <Text>Session status: idle · ready for a task</Text>;
    case 'starting':
      return <Text>Session status: starting · waiting for Python</Text>;
    case 'running':
      return (
        <Text>
          Session status: running · streaming response{canCancel ? ' · Esc to cancel' : ''}
        </Text>
      );
    case 'cancelling':
      return <Text color="yellow">Session status: cancelling · waiting for Python</Text>;
    case 'completed':
      return <Text color="green">Session status: completed · ready for another task</Text>;
    case 'cancelled':
      return <Text color="yellow">Session status: cancelled · ready for another task</Text>;
    case 'protocol-failed':
      return <Text color="red">Session status: protocol failed · {state.protocolFailure}</Text>;
  }
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
  if (
    sessionState.status === 'starting' ||
    sessionState.status === 'running' ||
    sessionState.status === 'cancelling'
  ) {
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

function RuntimeStatus({state}: {readonly state: RuntimeState}): ReactElement {
  switch (state.status) {
    case 'starting':
      return <Text>Status: starting Python runtime · workspace: {state.workspace}</Text>;
    case 'running':
      return <Text>Status: runtime running · workspace: {state.workspace} · Ctrl+C to exit</Text>;
    case 'failed-to-start':
      return (
        <Text color="red">
          Status: runtime failed to start · {state.message} · Ctrl+C to exit
        </Text>
      );
    case 'protocol-failed':
      return (
        <Text color="red">
          Status: runtime protocol failed ({state.code}) · {state.message} · Ctrl+C to exit
        </Text>
      );
    case 'unexpectedly-exited':
      return (
        <Text color="red">
          Status: runtime failed · {state.message} · Ctrl+C to exit
        </Text>
      );
    case 'stopping':
      return <Text>Status: stopping Python runtime…</Text>;
    case 'stopped':
      return <Text>Status: Python runtime stopped.</Text>;
  }
}
