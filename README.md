<p align="center">
<img width="500" height="258" alt="logo_500" src="https://github.com/user-attachments/assets/f0d1ff36-0bda-450a-9048-f90957b7abd5" />
<br/>
<a href=https://pypi.org/project/agent-cli-helper><img src=https://badge.fury.io/py/agent-cli-helper.svg/></a>
</p>

- **[llms.md](llms.md)** - Documentation for LLMs and agents
- **[humans.md](humans.md)** - Documentation of human-only tools (IMPORTANT: agents should ignore this file)

agent-cli-helper gives LLMs a way to use interactive terminal applications:

- **run-command** - Start a program in an interactive session
- **send-keystrokes** - Control the program
- **get-screen-capture** - See what's on screen
- **process-info** - Check if session is alive
- **kill-session** - Clean up when done

For humans: Using this is easy: Tell your harness (opencode, claude code, qwen, amp, gemini etc ... to run `uvx agent-cli-helper` before asking it to do complicated things)

## Examples

```bash
# Run a command in an interactive session
agent-cli-helper run-command "vim file.txt"

# Send keystrokes to control the program
agent-cli-helper send-keystrokes vim-file-txt "iHello\nEscape"

# View current screen
agent-cli-helper get-screen-capture vim-file-txt

# List all sessions
agent-cli-helper list-sessions
```

See [llms.md](llms.md) for detailed documentation.
