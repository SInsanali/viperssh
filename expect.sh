#!/usr/bin/expect -f

# ==== CONFIGURATION ====
set timeout -1

# Destination is first argument
set dest [lindex $argv 0]

if {$dest eq ""} {
    puts "Usage: $argv0 host"
    exit 1
}

# Cached password (empty until first prompt)
set cached_password ""

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

# ==== START SSH SESSION ====
spawn ssh $dest

# ==== HANDLE PROMPTS ====
expect {
    -re "(yes/no|fingerprint)" {
        send "yes\r"
        exp_continue
    }

    -re "\[Pp\]assword:" {
        if {$cached_password eq ""} {
            # First password prompt - ask user and cache it
            set cached_password [read_password]
        }

        # Send cached password
        send "$cached_password\r"
        exp_continue
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

# Clear password from memory before interactive mode
set cached_password ""

interact {
    -timeout 180 {
        send " \b"
    }
}
