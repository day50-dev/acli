<p align="center">
<img width="500" height="249" alt="logo_500" src="https://github.com/user-attachments/assets/ee093429-0a47-4a88-b66e-6a1931cab60e" />
</p>

- **[llms.md](llms.md)** - Documentation for LLMs and agents
- **[humans.md](humans.md)** - Documentation of human-only tools (IMPORTANT: agents should ignore this file)

cli-tool gives LLMs a way to use interactive terminal applications:

- **run-command** - Start a program in an interactive session
- **send-keystrokes** - Control the program
- **get-screen-capture** - See what's on screen
- **process-info** - Check if session is alive
- **kill-session** - Clean up when done

## Examples

```bash
# Run a command in an interactive session
cli-tool run-command "vim file.txt"

# Send keystrokes to control the program
cli-tool send-keystrokes vim-file-txt "iHello\nEscape"

# View current screen
cli-tool get-screen-capture vim-file-txt

# List all sessions
cli-tool list-sessions
```

See [llms.md](llms.md) for detailed documentation.
