import {Box, Text, useInput} from 'ink';
import type {ReactElement} from 'react';

/**
 * Render the static, conversation-first CAH-002 terminal shell.
 *
 * The component listens for terminal input so the shell remains mounted. Ink owns Ctrl+C cleanup;
 * task submission, runtime events, orchestration, and policy decisions are intentionally absent.
 *
 * @returns The initial title, conversation, task-input, and status regions.
 */
export function App(): ReactElement {
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
        <Text>Status: idle · runtime not connected · Ctrl+C to exit</Text>
      </Box>
    </Box>
  );
}
