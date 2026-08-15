#!/usr/bin/env python3
"""
VaporRAM — Shell Autocompletion Generator (Bash / Zsh)
Generates shell completion scripts for `vapor` CLI subcommands.
"""
import sys

BASH_COMPLETION = """# VaporRAM Bash Autocompletion
_vapor_completion() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    opts="doctor plan bench profile inspect config lan share stop presets init-config download run chat serve web completion release"

    if [ $COMP_CWORD -eq 1 ]; then
        COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
        return 0
    fi
}
complete -F _vapor_completion vapor
"""

ZSH_COMPLETION = """# VaporRAM Zsh Autocompletion
#compdef vapor

_vapor() {
    local -a commands
    commands=(
        'doctor:Run system and hardware diagnostics'
        'plan:Display memory budget breakdown (< 1.5 GB RAM)'
        'bench:Run performance & RAM benchmark'
        'profile:Run high-precision RAM memory profiler'
        'inspect:Inspect model weight files and tensor layout'
        'config:Run interactive terminal configuration wizard'
        'lan:Display LAN IP and network sharing instructions'
        'share:Show the URL, API key and client snippets for other devices'
        'stop:Stop a running VaporRAM server'
        'presets:List available persona presets'
        'init-config:Create default vapor.json configuration file'
        'download:Download google/gemma-4-E4B-it weights'
        'run:One-shot prompt generation'
        'chat:Interactive terminal chat session'
        'serve:Host LAN HTTP API server'
        'web:Launch server and open Web UI in browser'
        'release:Create distribution tarball package'
    )
    _describe 'vapor commands' commands
}
_vapor "$@"
"""

def generate(shell="bash"):
    if shell.lower() == "zsh":
        print(ZSH_COMPLETION)
    else:
        print(BASH_COMPLETION)

if __name__ == "__main__":
    sh = sys.argv[1] if len(sys.argv) > 1 else "bash"
    generate(sh)
