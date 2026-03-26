<p align="center">
<img width="500" height="249" alt="logo_500" src="https://github.com/user-attachments/assets/ee093429-0a47-4a88-b66e-6a1931cab60e" />
</p>

- **[llms.md](llms.md)** - Documentation for LLMs and agents
- **[humans.md](humans.md)** - Documentation for human users (IMPORTANT: agents should ignore this file)

## Quick Start

```bash
# Run a command in an interactive session
./cb/cli-tool run-command "vim file.txt"

# Send keystrokes to control the program
./cb/cli-tool send-keystrokes vim-file "iHello\nEscape"

# View current screen
./cb/cli-tool get-screen-capture vim-file

# List all sessions
./cb/cli-tool list-sessions

# Manage sessions (for humans)
./cb/cli-manage
```

## What is cli-tool?

cli-tool wraps tmux to give LLMs an easier way to use terminal applications:

- **run-command** - Start a program in an interactive session
- **send-keystrokes** - Control the program
- **get-screen-capture** - See what's on screen
- **process-info** - Check if session is alive
- **kill-session** - Clean up when done

See [llms.md](llms.md) for detailed documentation.

## cli-manage

For humans to manage sessions across all agent instances. Shows:
- Tree view of all sessions
- Liveness check on parent processes
- Idle timers
- Glob pattern support for bulk operations

See [humans.md](humans.md) for details.
