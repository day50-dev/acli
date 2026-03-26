# Todo: cli-tool Implementation

## Phase 1: Setup
- [x] Check tmux is installed (v3.6 ✓)
- [ ] Create cb/ directory structure
- [ ] Set up Python project (requirements.txt, __init__.py)

## Phase 2: Core Implementation
- [ ] Implement main CLI entry point with argparse
- [ ] Implement `new-command` command - start tmux session with command
- [ ] Implement `send-keystrokes` command - send keys to session
- [ ] Implement `process-info` command - get process metadata
- [ ] Implement `kill-all-tools` command - kill sessions

## Phase 3: Features
- [ ] Add `--agent` flag for namespace scoping
- [ ] Add `--global` flag for viewing all sessions
- [ ] Add environment variable handling (AGENT_NAME, SESSION_ID)
- [ ] Add XML output formatting

## Phase 4: Testing
- [ ] Write unit tests for core functions
- [ ] Test with real tmux sessions (nano, vim, etc.)
- [ ] Test keystroke sending
- [ ] Test process info retrieval

## Phase 5: Polish
- [ ] Add help documentation
- [ ] Verify all commands work as expected
- [ ] Clean up and finalize