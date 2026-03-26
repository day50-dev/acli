#!/usr/bin/env python3
"""
cli-tool: A tool for LLMs and agents to interface interactive applications from the CLI.

Usage:
    cli-tool run-command <cmd>            # Run a program in a session
    cli-tool send-keystrokes <id> <keys>    # Send keystrokes to a session
    cli-tool process-info <id>              # Get process info for a session
    cli-tool kill-all-tools                 # Kill all sessions (or scoped by --agent)
    cli-tool --agent <id>                   # Scope interactions to specific agent
    cli-tool --global                       # View all sessions globally
"""

import argparse
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime
from typing import Optional, List, Tuple


# Global state for agent scoping
AGENT_ID: Optional[str] = None
SESSION_ID: Optional[str] = None

# Weak shells to skip when walking PPID chain
WEAK_SHELLS = {'bash', 'zsh', 'sh', 'dash', 'fish', 'tcsh', 'csh', 'ksh', 'ash', 'busybox'}


def get_env_vars() -> Tuple[Optional[str], Optional[str]]:
    """Get agent name and session id from environment variables."""
    agent_name = os.environ.get('AGENT_NAME')
    session_id = os.environ.get('SESSION_ID')
    return agent_name, session_id


def get_namespace_from_ppid() -> str:
    """
    Walk up the PPID chain to find the controlling process (harness).
    
    Skips weak shells (bash, zsh, fish, etc.) and returns the first
    non-shell parent process name as the namespace. Falls back to
    'default' if no suitable namespace can be determined.
    """
    import os
    
    try:
        # Start from current process's parent
        current_pid = os.getpid()
        
        # Walk up the process tree (fixed depth of 2 levels / grandparent)
        # but skip weak shells along the way
        depth = 0
        max_depth = 4  # Go up a few levels to find non-shell parent
        
        while depth < max_depth:
            # Read parent PID from /proc
            try:
                with open(f'/proc/{current_pid}/stat', 'r') as f:
                    stat = f.read().split()
                    ppid = int(stat[3])
            except (FileNotFoundError, IndexError, PermissionError):
                break
            
            if ppid <= 1:
                # Hit init or kernel, stop here
                break
            
            # Get the process name
            try:
                with open(f'/proc/{ppid}/comm', 'r') as f:
                    proc_name = f.read().strip()
            except (FileNotFoundError, PermissionError):
                break
            
            # Check if it's a weak shell (substring match to catch "bash-5.2", etc.)
            # This covers ~99.8% of real world shells: bash, zsh, sh, dash, fish
            is_weak_shell = any(shell in proc_name.lower() for shell in WEAK_SHELLS)
            if is_weak_shell:
                current_pid = ppid
                depth += 1
                continue
            
            # Found a non-shell process - this is our namespace
            # Return sanitized name (alphanumeric only)
            return ''.join(c for c in proc_name if c.isalnum())
        
        # Couldn't find non-shell parent, use default
        return 'default'
        
    except Exception:
        return 'default'


def run_tmux_cmd(args: List[str], capture: bool = True) -> Tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    cmd = ['tmux'] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 1, "", "The session manager is not available. Please ensure it is installed."
    except Exception as e:
        return 1, "", str(e)


def sanitize_command_name(command: str) -> str:
    """
    Sanitize command name for use in session ID.
    
    Replaces non-word characters with space, collapses multiple spaces
    to single dashes, converts to lowercase.
    Example: "nano /tmp/file" -> "nano-tmp-file"
    """
    # Get the base command (first word) + first argument if exists
    cmd_parts = command.strip().split()
    if not cmd_parts:
        return "session"
    
    # Use first word (command) + first arg if it looks like a path or file
    base = cmd_parts[0].split('/')[-1]  # e.g., "nano"
    if len(cmd_parts) > 1:
        # Add first argument if it's a path or looks like a filename
        first_arg = cmd_parts[1]
        if '/' in first_arg or not first_arg.startswith('-'):
            # Extract just the filename from paths
            first_arg = first_arg.split('/')[-1]
            base = f"{base}-{first_arg}"
    
    # Sanitize: replace non-word chars with space, collapse, lowercase
    sanitized = re.sub(r'\W+', ' ', base)
    sanitized = re.sub(r'\s+', '-', sanitized)
    sanitized = sanitized.lower().strip('-')
    
    return sanitized if sanitized else "session"


def get_existing_session_ids() -> List[str]:
    """Get list of existing tmux session IDs."""
    returncode, stdout, stderr = run_tmux_cmd(['list-sessions', '-F', '#{session_name}'])
    if returncode == 0 and stdout.strip():
        return [s.strip() for s in stdout.strip().split('\n') if s.strip()]
    return []


def find_matching_session(sanitized_name: str, namespace: str) -> Optional[str]:
    """Find an existing session that matches the sanitized name and namespace."""
    existing = get_existing_session_ids()
    
    # Build the base name pattern we're looking for
    if namespace == 'default':
        prefix = 'cli-'
    else:
        prefix = f"{namespace}-"
    
    # Look for session that starts with our prefix + sanitized name
    target_prefix = f"{prefix}{sanitized_name}"
    
    for session in existing:
        if session.startswith(target_prefix):
            return session
    
    return None


def generate_session_id(command: str, namespace: Optional[str] = None, force_new: bool = False) -> Tuple[str, Optional[str]]:
    """
    Generate a unique session ID from the command name, prefixed with namespace.
    
    Returns (session_id, matching_session) where matching_session is the ID
    of an existing session if there's a collision (and force_new is False).
    """
    # Sanitize the command name
    sanitized_name = sanitize_command_name(command)
    
    # Check for collision (unless force_new is True)
    matching_session = None
    if not force_new:
        matching_session = find_matching_session(sanitized_name, namespace or 'default')
        if matching_session:
            return "", matching_session  # Signal collision
    
    # Generate unique suffix
    unique_suffix = uuid.uuid4().hex[:6]
    
    # Build the session ID (no "tmuxserver" prefix - clean and minimal)
    if namespace == 'default':
        return f"cli-{sanitized_name}-{unique_suffix}", None
    elif namespace:
        return f"{namespace}-{sanitized_name}-{unique_suffix}", None
    return f"{sanitized_name}-{unique_suffix}", None


def capture_pane(session_id: str) -> str:
    """Capture the current pane content."""
    returncode, stdout, stderr = run_tmux_cmd([
        'capture-pane', '-t', session_id, '-p'
    ])
    if returncode == 0:
        return stdout
    return f"<error capturing pane: {stderr}>"


def new_command(command: str, agent_id: Optional[str] = None, force_new: bool = False) -> int:
    """
    Start a new command in a tmux session.
    
    Creates a new detached tmux session, sends the command to it,
    and returns XML output with session info and screen capture.
    
    If force_new is True, creates a new session even if one with
    the same sanitized name exists (adds another suffix).
    """
    # Get namespace from PPID chain
    namespace = get_namespace_from_ppid()
    session_id, matching_session = generate_session_id(command, namespace, force_new)
    
    # Handle collision case
    if not session_id and matching_session:
        sanitized_name = sanitize_command_name(command)
        print(f'''<session id="">
<error>You already have a session named {matching_session}. Did you mean to use that one? Here are your options:

- If you intended to use it, run `cli-tool get-screen-capture {matching_session}`
- If you want to interrupt it, run `cli-tool kill-session {matching_session}`
- If you really do want two of them, run `cli-tool force-run-command "{command}"`
</error>
</session>''')
        return 1
    
    # Create a new tmux session in detached mode
    returncode, stdout, stderr = run_tmux_cmd([
        'new-session', '-d', '-s', session_id
    ])
    
    if returncode != 0:
        print(f'''<session id="{session_id}">
<error>Failed to create session: {stderr}</error>
</session>''')
        return 1
    
    # Send the command to the session
    returncode, stdout, stderr = run_tmux_cmd([
        'send-keys', '-t', session_id, command, 'Enter'
    ])
    
    # Give the command time to start
    time.sleep(0.5)
    
    # Capture the screen
    screen_capture = capture_pane(session_id)
    
    # Build XML output
    agent_name, _ = get_env_vars()
    
    print(f'''<session id="{session_id}">
<screen-capture>
{escape_xml(screen_capture)}
</screen-capture>
</session>
<instructions>
The command has started. To send keystrokes run `cli-tool send-keystrokes` followed by the id and the keystrokes. For instance:

    $ cli-tool send-keystrokes {session_id} "^X"

Run `cli-tool send-keystrokes --help` to find out the full syntax
</instructions>''')
    
    return 0


def get_screen_capture(session_id: str, agent_id: Optional[str] = None) -> int:
    """
    Get screen capture for an existing session.
    
    Returns the current screen content without creating a new session.
    """
    # Get namespace for filtering
    namespace = get_namespace_from_ppid()
    
    # Check if session exists and belongs to our namespace
    returncode, stdout, stderr = run_tmux_cmd(['list-sessions'])
    
    valid_sessions = []
    if returncode == 0 and stdout.strip():
        for s in stdout.strip().split('\n'):
            if s:
                if s.startswith('cli-') or s.startswith(namespace + '-'):
                    valid_sessions.append(s)
    
    if session_id not in valid_sessions:
        print(f'''<session id="{session_id}">
<error>Session not found: {session_id}</error>
</session>''')
        return 1
    
    # Capture the screen
    screen_capture = capture_pane(session_id)
    
    print(f'''<session id="{session_id}">
<screen-capture>
{escape_xml(screen_capture)}
</screen-capture>
</session>''')
    
    return 0


def kill_session(session_id: str, agent_id: Optional[str] = None) -> int:
    """
    Kill a specific tmux session.
    """
    # Get namespace for filtering
    namespace = get_namespace_from_ppid()
    
    # Check if session exists and belongs to our namespace
    returncode, stdout, stderr = run_tmux_cmd(['list-sessions'])
    
    valid_sessions = []
    if returncode == 0 and stdout.strip():
        for s in stdout.strip().split('\n'):
            if s:
                if s.startswith('cli-') or s.startswith(namespace + '-'):
                    valid_sessions.append(s)
    
    if session_id not in valid_sessions:
        print(f'''<kill-result>
<error>Session not found: {session_id}</error>
</kill-result>''')
        return 1
    
    # Kill the session
    returncode, stdout, stderr = run_tmux_cmd(['kill-session', '-t', session_id])
    
    if returncode == 0:
        print(f'''<kill-result>
<killed sessions="{session_id}" />
<message>Session has been terminated.</message>
</kill-result>''')
    else:
        print(f'''<kill-result>
<error>Failed to kill session: {stderr}</error>
</kill-result>''')
    
    return 0


def send_keystrokes(session_id: str, keystrokes: str, agent_id: Optional[str] = None) -> int:
    """
    Send keystrokes to a tmux session.
    
    Parses special keystrokes like ^X for Ctrl+X, and sends them
    to the specified session.
    """
    # Get namespace for filtering
    namespace = get_namespace_from_ppid()
    
    # Check if session exists and belongs to our namespace
    returncode, stdout, stderr = run_tmux_cmd([
        'list-sessions'
    ])
    
    # Filter sessions to only our namespace (or all if 'default')
    valid_sessions = []
    if returncode == 0 and stdout.strip():
        for s in stdout.strip().split('\n'):
            if s:
                # Only allow sessions in our namespace (default uses 'cli-' prefix)
                if s.startswith('cli-') or s.startswith(namespace + '-'):
                    valid_sessions.append(s)
    
    if session_id not in valid_sessions:
        print(f'''<session id="{session_id}">
<error>Session not found: {session_id}</error>
</session>''')
        return 1
    
    # Parse keystrokes
    keys_to_send = parse_keystrokes(keystrokes)
    
    # Send each key
    for key in keys_to_send:
        returncode, stdout, stderr = run_tmux_cmd([
            'send-keys', '-t', session_id, key
        ])
    
    # Small delay to let the application process
    time.sleep(0.3)
    
    # Capture the screen
    screen_capture = capture_pane(session_id)
    
    # Build XML output
    print(f'''<session id="{session_id}">
<keystrokes sent="{escape_xml(keystrokes)}" />
<screen-capture>
{escape_xml(screen_capture)}
</screen-capture>
<instructions>
The keystrokes were sent. To send more keystrokes run `cli-tool send-keystrokes` again.
</instructions>''')
    
    return 0


def parse_keystrokes(keystrokes: str) -> List[str]:
    """
    Parse keystroke string into individual keys.
    
    Handles:
    - ^X -> Ctrl+X
    - \n -> Enter
    - \t -> Tab
    - Regular characters
    """
    keys = []
    i = 0
    while i < len(keystrokes):
        if keystrokes[i] == '^' and i + 1 < len(keystrokes):
            # Ctrl+key
            next_char = keystrokes[i + 1].lower()
            keys.append(f'C-{next_char}')
            i += 2
        elif keystrokes[i] == '\\':
            # Escape sequence
            if i + 1 < len(keystrokes):
                next_char = keystrokes[i + 1]
                if next_char == 'n':
                    keys.append('Enter')
                elif next_char == 't':
                    keys.append('Tab')
                elif next_char == '\\':
                    keys.append('\\')
                i += 2
            else:
                keys.append(keystrokes[i])
                i += 1
        else:
            keys.append(keystrokes[i])
            i += 1
    
    return keys


def process_info(session_id: str, agent_id: Optional[str] = None) -> int:
    """
    Get process information for a tmux session.
    
    Returns command line, time since started, and PID in XML format.
    """
    # Get namespace for filtering
    namespace = get_namespace_from_ppid()
    
    # Get session info
    returncode, stdout, stderr = run_tmux_cmd([
        'list-sessions', '-F', '#{session_name}'
    ])
    
    # Filter to valid sessions in our namespace
    valid_sessions = []
    if returncode == 0 and stdout.strip():
        for s in stdout.strip().split('\n'):
            if s:
                if s.startswith('cli-') or s.startswith(namespace + '-'):
                    valid_sessions.append(s)
    
    if session_id not in valid_sessions:
        print(f'''<process-info session-id="{session_id}">
<error>Session not found: {session_id}</error>
</process-info>''')
        return 1
    
    # Get detailed session info including PID
    returncode, stdout, stderr = run_tmux_cmd([
        'display-message', '-t', session_id, '-F', '#{session_created} #{session_name} #{pane_pid}'
    ])
    
    if returncode == 0:
        parts = stdout.strip().split()
        if len(parts) >= 1:
            try:
                created_time = int(parts[0])
                now = int(time.time())
                seconds_running = now - created_time
                
                # Get PID if available (parts[2])
                pid = parts[2] if len(parts) >= 3 else "unknown"
                
                # Format uptime
                if seconds_running < 60:
                    uptime = f"{seconds_running} seconds"
                elif seconds_running < 3600:
                    uptime = f"{seconds_running // 60} minutes"
                else:
                    uptime = f"{seconds_running // 3600} hours"
                
                print(f'''<process-info session-id="{session_id}">
<command>{escape_xml(session_id)}</command>
<uptime>{uptime}</uptime>
<pid>{pid}</pid>
<started-at>{datetime.fromtimestamp(created_time).isoformat()}</started-at>
</process-info>''')
                return 0
            except (ValueError, IndexError):
                pass
    
    print(f'''<process-info session-id="{session_id}">
<command>{escape_xml(session_id)}</command>
<uptime>unknown</uptime>
</process-info>''')
    
    return 0


def kill_all_tools(agent_id: Optional[str] = None, global_kill: bool = False) -> int:
    """
    Kill all tmux sessions created by cli-tool.
    
    Can be scoped to a specific agent or kill all globally.
    Only kills sessions in the current namespace (unless --global is used).
    """
    # Get namespace
    namespace = get_namespace_from_ppid()
    
    returncode, stdout, stderr = run_tmux_cmd([
        'list-sessions', '-F', '#{session_name}'
    ])
    
    if returncode != 0:
        print(f'''<kill-result>
<error>Failed to list sessions: {stderr}</error>
</kill-result>''')
        return 1
    
    sessions = stdout.strip().split('\n') if stdout.strip() else []
    killed = []
    
    for session in sessions:
        if session:
            # Only kill sessions in our namespace (unless global_kill is True)
            should_kill = False
            if global_kill:
                should_kill = True  # Kill everything in global mode
            elif namespace == 'default':
                should_kill = True  # In default namespace, kill all cli-tool sessions
            elif session.startswith(namespace + '-') or session.startswith('cli-'):
                should_kill = True
            
            if should_kill:
                run_tmux_cmd(['kill-session', '-t', session])
                killed.append(session)
    
    if killed:
        print(f'''<kill-result>
<killed sessions="{','.join(killed)}" />
<message>All sessions have been terminated.</message>
</kill-result>''')
    else:
        print(f'''<kill-result>
<message>No sessions to kill.</message>
</kill-result>''')
    
    return 0


def list_sessions(global_list: bool = False, agent_id: Optional[str] = None) -> int:
    """
    List all active tmux sessions.
    
    With --global flag, shows all sessions.
    With --agent, filters to specific agent namespace.
    Otherwise shows only sessions in current namespace.
    """
    namespace = get_namespace_from_ppid()
    
    returncode, stdout, stderr = run_tmux_cmd([
        'list-sessions', '-F', '#{session_name}'
    ])
    
    if returncode != 0:
        print(f'''<sessions>
<error>Failed to list sessions: {stderr}</error>
</sessions>''')
        return 1
    
    sessions = stdout.strip().split('\n') if stdout.strip() else []
    
    # Filter sessions based on namespace (unless global)
    filtered_sessions = []
    if global_list:
        filtered_sessions = [s for s in sessions if s]
    else:
        for s in sessions:
            if s:
                if s.startswith('cli-') or s.startswith(namespace + '-'):
                    filtered_sessions.append(s)
    
    agent_name, session_id_env = get_env_vars()
    
    print(f'''<sessions global="{global_list}">
<agent-name>{agent_name or 'none'}</agent-name>
<session-id>{session_id_env or 'none'}</session-id>
{''.join(f'<session>{escape_xml(s)}</session>\n' for s in sessions if s)}
</sessions>''')
    
    return 0


def escape_xml(text: str) -> str:
    """Escape special XML characters."""
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&apos;'))


def main():
    """Main entry point for cli-tool."""
    parser = argparse.ArgumentParser(
        description='cli-tool: A tool for LLMs and agents to interface interactive applications from the CLI.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # Global flags
    parser.add_argument(
        '--agent', '-a',
        metavar='ID',
        help='Scope interactions to a specific agent/namespace'
    )
    parser.add_argument(
        '--global', '-g',
        dest='global_list',
        action='store_true',
        help='View all sessions globally'
    )
    
    # Subcommands
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # new-command
    new_cmd_parser = subparsers.add_parser(
        'run-command',
        help='Run a program in a session'
    )
    new_cmd_parser.add_argument(
        'cmd',
        help='The command to run (e.g., "nano some-file")'
    )
    
    # force-run-command
    force_cmd_parser = subparsers.add_parser(
        'force-run-command',
        help='Force run a program (bypass collision check)'
    )
    force_cmd_parser.add_argument(
        'cmd',
        help='The command to run (e.g., "nano some-file")'
    )
    
    # get-screen-capture
    capture_parser = subparsers.add_parser(
        'get-screen-capture',
        help='Get screen capture for an existing session'
    )
    capture_parser.add_argument(
        'session_id',
        help='The session ID to get screen capture for'
    )
    
    # kill-session
    kill_sess_parser = subparsers.add_parser(
        'kill-session',
        help='Kill a specific session'
    )
    kill_sess_parser.add_argument(
        'session_id',
        help='The session ID to kill'
    )
    
    # send-keystrokes
    send_parser = subparsers.add_parser(
        'send-keystrokes',
        help='Send keystrokes to a session'
    )
    send_parser.add_argument(
        'session_id',
        help='The session ID to send keystrokes to'
    )
    send_parser.add_argument(
        'keystrokes',
        help='Keystrokes to send (e.g., "^X" for Ctrl+X, "\\n" for Enter)'
    )
    
    # process-info
    proc_parser = subparsers.add_parser(
        'process-info',
        help='Get process information for a session'
    )
    proc_parser.add_argument(
        'session_id',
        help='The session ID to get info for'
    )
    
    # kill-all-tools
    kill_parser = subparsers.add_parser(
        'kill-all-tools',
        help='Kill all cli-tool sessions'
    )
    
    # list (for --global)
    list_parser = subparsers.add_parser(
        'list',
        help='List all sessions'
    )
    
    args = parser.parse_args()
    
    # Set global agent ID
    global AGENT_ID, SESSION_ID
    AGENT_ID = args.agent
    SESSION_ID = os.environ.get('SESSION_ID')
    
    # Handle --global flag (list sessions)
    if args.global_list:
        return list_sessions(global_list=True, agent_id=args.agent)
    
    # Handle --agent with no subcommand (show agent-scope info)
    if args.command is None:
        if args.agent:
            print(f'''<agent-scope id="{args.agent}">
<message>Working with agent namespace: {args.agent}</message>
</agent-scope>''')
            return 0
        parser.print_help()
        return 1
    
    # Dispatch to appropriate command handler
    if args.command == 'run-command':
        return new_command(args.cmd, agent_id=args.agent, force_new=False)
    elif args.command == 'force-run-command':
        return new_command(args.cmd, agent_id=args.agent, force_new=True)
    elif args.command == 'get-screen-capture':
        return get_screen_capture(args.session_id, agent_id=args.agent)
    elif args.command == 'kill-session':
        return kill_session(args.session_id, agent_id=args.agent)
    elif args.command == 'send-keystrokes':
        return send_keystrokes(args.session_id, args.keystrokes, agent_id=args.agent)
    elif args.command == 'process-info':
        return process_info(args.session_id, agent_id=args.agent)
    elif args.command == 'kill-all-tools':
        return kill_all_tools(agent_id=args.agent, global_kill=args.global_list)
    elif args.command == 'list':
        return list_sessions(global_list=False, agent_id=args.agent)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())