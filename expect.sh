#!/usr/bin/expect -f

# ==== CONFIGURATION ====
set timeout -1

# Destination is first argument, protocol is optional second (default: ssh)
set dest [lindex $argv 0]
set proto [lindex $argv 1]
if {$proto eq ""} {
    set proto "ssh"
}

if {$dest eq ""} {
    puts "Usage: $argv0 host \[ssh|sftp\]"
    exit 1
}

# Cached password (empty until first prompt)
set cached_password ""

# Vault password tracking
set vault_password_used 0
set vault_password_failed 0
set password_attempts 0

if {[info exists env(VIPER_PASSWORD)]} {
    set cached_password $env(VIPER_PASSWORD)
    set vault_password_used 1
    # Debug (uncomment to trace vault password injection):
    # set _sum 0; foreach _c [split $cached_password ""] { scan $_c %c _code; incr _sum $_code }
    # puts "\[DEBUG\] VIPER_PASSWORD len=[string length $cached_password] sum=$_sum"
    unset env(VIPER_PASSWORD)
}

# Handle Ctrl+C - restore terminal and exit cleanly
trap {
    stty echo
    puts "\nCancelled."
    exit 130
} SIGINT

# Procedure to read password with Ctrl+C support
proc read_password {} {
    stty -echo
    puts -nonewline "Password: "
    flush stdout

    set password ""
    # Use expect_user with timeout to allow signal checking
    expect_user {
        -timeout 1
        timeout {
            exp_continue
        }
        -re "(\[^\r\n]*)\[\r\n]" {
            set password $expect_out(1,string)
        }
        eof {
            stty echo
            puts "\nCancelled."
            exit 130
        }
    }

    puts ""
    stty echo
    return $password
}

# Track if we successfully reached a shell
set reached_shell 0

# Suppress banner/MOTD output
log_user 0

# ==== START SESSION ====
# Skip key-based auth to avoid "Too many authentication failures" when
# the ssh-agent has multiple keys loaded and the server has low MaxAuthTries.
spawn $proto -o PreferredAuthentications=keyboard-interactive,password -o ServerAliveInterval=60 -o ServerAliveCountMax=3 $dest

# Handle window resize - propagate to spawned process
trap {
    set size [exec stty size < /dev/tty]
    set rows [lindex $size 0]
    set cols [lindex $size 1]
    stty rows $rows columns $cols < $spawn_out(slave,name)
} WINCH

# ==== HANDLE PROMPTS ====
expect {
    -re "(yes/no|fingerprint)" {
        send "yes\r"
        exp_continue
    }

    -re {[Nn]ew [Pp]assword} {
        # Forced password change - clear cached password and hand off to user
        set cached_password ""
        log_user 1
        puts "\n\[VIPERSSH\] Password change required. Complete it manually.\n"
        send_user $expect_out(0,string)
        interact {
            -timeout 180 {
                send " \b"
            }
        }
        exit 0
    }

    -re "\[Pp\]assword:" {
        incr password_attempts
        if {$cached_password eq ""} {
            # No password yet - ask user and cache it
            set cached_password [read_password]
            send "$cached_password\r"
            exp_continue
        } elseif {$password_attempts > 2 && $vault_password_used && !$vault_password_failed} {
            # Vault password rejected after multiple rounds, ask user
            set vault_password_failed 1
            set cached_password ""
            set cached_password [read_password]
            # Debug (uncomment to trace user-typed password):
            # set _sum 0; foreach _c [split $cached_password ""] { scan $_c %c _code; incr _sum $_code }
            # puts "\[DEBUG\] user typed: len=[string length $cached_password] sum=$_sum"
            send "$cached_password\r"
            exp_continue
        } else {
            send "$cached_password\r"
            exp_continue
        }
    }

    eof {
        # Show any buffered output if we never reached the shell
        if {!$reached_shell && [info exists expect_out(buffer)]} {
            set output [string trim $expect_out(buffer)]
            if {$output ne ""} {
                puts $output
            }
        }
        exit 0
    }

    # Shell prompt detection - re-enable output and hand off
    -re {[$#%>] $} {
        set reached_shell 1
        log_user 1
        send "\r"
    }
}

# Determine exit code based on vault usage
if {$vault_password_failed} {
    set viper_exit 12
} elseif {$vault_password_used} {
    set viper_exit 10
} else {
    set viper_exit 11
}

# Prompt to save/update password right after successful login
if {[info exists env(VIPER_PW_FD)] && $cached_password ne ""} {
    set pw_fd $env(VIPER_PW_FD)
    set should_prompt 0

    if {$viper_exit == 11} {
        # User typed password manually, vault has no saved pw for this env
        set should_prompt 1
        set prompt_msg "\n\[VAULT\] Save password? (y/n) "
    } elseif {$viper_exit == 12} {
        # Vault password failed, user typed a new one
        set should_prompt 1
        set prompt_msg "\n\[VAULT\] Update saved password? (y/n) "
    }

    if {$should_prompt} {
        puts -nonewline $prompt_msg
        flush stdout
        expect_user {
            -re "(\[^\r\n]*)\[\r\n]" {
                set answer $expect_out(1,string)
            }
        }
        puts ""

        if {[string tolower [string trim $answer]] eq "y"} {
            # Debug (uncomment to trace pipe write):
            # set _sum 0; foreach _c [split $cached_password ""] { scan $_c %c _code; incr _sum $_code }
            # puts "\[DEBUG\] writing to pipe: len=[string length $cached_password] sum=$_sum"
            if {[catch {
                set chan [open "/proc/self/fd/$pw_fd" w]
                puts -nonewline $chan $cached_password
                close $chan
            } err]} {
                puts "\[VAULT\] Failed to save: $err"
            } else {
                puts "\[VAULT\] Saved."
            }
        }
    }

    unset -nocomplain env(VIPER_PW_FD)
}

# Clear password from memory before interactive mode
set cached_password ""

puts "\033]0;$dest\007"
interact {
    -timeout 180 {
        send " \b"
    }
}

exit $viper_exit
