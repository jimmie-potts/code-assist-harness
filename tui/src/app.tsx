import {Box, Text, useInput} from 'ink';
import type {ReactElement} from 'react';

import type {RuntimeState} from './runtime-supervisor.js';

/** Runtime projection rendered by the terminal shell. */
export interface AppProperties {
  /** Current child lifecycle state; the component never decides or changes this state. */
  readonly runtimeState: RuntimeState;
}

/**
 * Render the conversation-first shell and its supervised Python runtime state.
 *
 * The component listens for terminal input so the shell remains mounted. Ink owns Ctrl+C cleanup;
 * task submission, protocol events, orchestration, and policy decisions are intentionally absent.
 *
 * @param properties - Projection-only runtime state supplied by the lifecycle owner.
 * @returns The initial title, conversation, task-input, and status regions.
 */
export function App({runtimeState}: AppProperties): ReactElement {
  useInput(() => undefined);

  return (
    <Box flexDirection="column" paddingX={1}>
      <Text bold color="cyan">
        Code Assist Harness
      </Text>

      <Box flexDirection="column" marginTop={1}>
        <Text bold>Conversation</Text>
        <Box borderStyle="round" paddingX={1}>
          <Text dimColor>No messages yet.</Text>
        </Box>
      </Box>

      <Box flexDirection="column" marginTop={1}>
        <Text bold>Task input</Text>
        <Box borderStyle="round" paddingX={1}>
          <Text dimColor>Input is not connected in this static shell.</Text>
        </Box>
      </Box>

      <Box marginTop={1}>
        <RuntimeStatus state={runtimeState} />
      </Box>
    </Box>
  );
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
