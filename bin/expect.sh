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

# Cached password: the target's, offered to the vault after login (empty
# until known)
set cached_password ""

# Passwords that have got a login through this run, newest first, and per
# login ("user@host") the one that last worked there
set known_passwords {}
array set login_password {}

# Vault password tracking
set vault_password ""
set vault_password_used 0
set vault_password_failed 0

# Forced password change: the replacement the user picked, and whether the
# server took it (cached_password switches over to it once it has)
set new_password ""
set password_changed 0

if {[info exists env(VIPER_PASSWORD)]} {
    set cached_password $env(VIPER_PASSWORD)
    set vault_password $cached_password
    set known_passwords [list $cached_password]
    set vault_password_used 1
    # Debug (uncomment to trace vault password injection):
    # set _sum 0; foreach _c [split $cached_password ""] { scan $_c %c _code; incr _sum $_code }
    # puts "\[DEBUG\] VIPER_PASSWORD len=[string length $cached_password] sum=$_sum"
    unset env(VIPER_PASSWORD)
}

# Restore the terminal and exit, tolerating an already-closed stdout/stderr
# (e.g. when the user sends EOF with Ctrl+D). Writing the message must never
# itself raise — otherwise we'd dump a Tcl stack trace instead of exiting.
proc clean_exit {code {msg ""}} {
    catch {stty echo}
    if {$msg ne ""} {
        if {[catch {puts $msg; flush stdout}]} {
            catch {puts stderr $msg}
        }
    }
    exit $code
}

# Handle Ctrl+C - restore terminal and exit cleanly
trap {
    clean_exit 130 "\nCancelled."
} SIGINT

# ==== STATUS OUTPUT ====
# Progress is shown as log-style steps, each finished with a status tag:
#
#   Connecting to app1.example.com ...................... [ OK ]
#
# step prints the message and leaves the line open while we wait on the
# server; step_done adds the tag once we know how it went. step_kind says what
# the open step is waiting on (route, connect, auth or change).
set RESET   "\033\[0m"
set DIM     "\033\[2m"
set RED     "\033\[1;31m"
set GREEN   "\033\[1;32m"
set YELLOW  "\033\[1;33m"
set MAGENTA "\033\[1;35m"
set CYAN    "\033\[1;36m"

set line_width 64
set step_open 0
set step_kind ""

proc step {msg {kind ""}} {
    global line_width step_open step_kind DIM RESET
    set dots [expr {max(3, $line_width - [string length $msg] - 10)}]
    puts -nonewline "  $msg $DIM[string repeat . $dots]$RESET "
    flush stdout
    set step_open 1
    set step_kind $kind
}

proc step_done {status} {
    global step_open step_kind auth_id sent_password RESET GREEN YELLOW RED
    if {!$step_open} {
        return
    }
    # However a login step ends up closed, OK means its password worked
    if {$status eq "OK" && $step_kind eq "auth"} {
        password_worked $auth_id $sent_password
    }
    switch -- $status {
        OK      { set tag "$GREEN OK $RESET" }
        WARN    { set tag "${YELLOW}WARN$RESET" }
        default { set tag "${RED}FAIL$RESET" }
    }
    puts "\[$tag\]"
    set step_open 0
    set step_kind ""
}

# A step whose outcome is already known
proc step_line {msg status} {
    step $msg
    step_done $status
}

# Detail under a step: server messages and hints
proc say {msg {color ""}} {
    global RESET
    if {$color ne ""} {
        set msg "$color$msg$RESET"
    }
    catch {puts "    $msg"}
}

# Non-blank lines of server output, minus the "(user@host) " prefix that
# keyboard-interactive puts on them
proc server_lines {text} {
    set lines {}
    foreach line [split [string map {"\r" ""} $text] "\n"] {
        regsub {^\(\S+@\S+\)\s*} $line "" line
        set line [string trim $line]
        if {$line ne ""} {
            lappend lines $line
        }
    }
    return $lines
}

# Procedure to read a password with Ctrl+C / Ctrl+D support
proc read_password {label} {
    stty -echo
    puts -nonewline "    $label: "
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
            # Ctrl+D / closed stdin — bail out cleanly.
            clean_exit 130 "\nCancelled."
        }
    }

    catch {puts ""}
    catch {stty echo}
    return $password
}

# Ask a y/n question; anything but y (or Ctrl+D) is no
proc ask_yes {prompt} {
    puts -nonewline $prompt
    flush stdout
    set answer ""
    expect_user {
        -re "(\[^\r\n]*)\[\r\n]" {
            set answer $expect_out(1,string)
        }
        eof {
            # Ctrl+D — take it as no. (Enter already ended the line; Ctrl+D doesn't.)
            catch {puts ""}
        }
    }
    return [expr {[string tolower [string trim $answer]] eq "y"}]
}

# ==== ROUTE ====
# Ask ssh how it will reach $dest (after ~/.ssh/config) so the steps can name
# the hosts involved: target_names are the names the target's login prompt may
# use, jump_via the hop(s) in front of it. Without -G we show generic steps.
set target_label [regsub {^.*@} $dest ""]
set target_host $target_label
set target_names [list [string tolower $target_label]]
set login_user ""
set jump_via ""
if {![catch {exec ssh -G $dest 2>/dev/null} ssh_config]} {
    foreach line [split $ssh_config "\n"] {
        set value [string trim [string range $line [string first " " $line] end]]
        switch -- [lindex [split $line] 0] {
            user {
                set login_user $value
            }
            hostname {
                set target_host $value
                lappend target_names [string tolower $value]
            }
            hostkeyalias {
                lappend target_names [string tolower $value]
            }
            proxyjump {
                set jump_via $value
            }
            proxycommand {
                # The classic jump "ssh -W %h:%p bastion" hops via its last argument
                if {[regexp {^\S*ssh\s.*-W\s} $value]} {
                    regexp {(\S+)\s*$} $value -> jump_via
                } elseif {$value ne "none"} {
                    set jump_via "proxy command"
                }
            }
        }
    }
}

# A lone jump host's name ("[user@]host[:port]" stripped to the host), so its
# steps can use it the way the target's use target_label
set jump_host ""
if {$jump_via ne "proxy command" && ![string match *,* $jump_via]} {
    regsub {^ssh://} $jump_via "" jump_host
    regsub {^.*@} $jump_host "" jump_host
    regsub {:[0-9]+$} $jump_host "" jump_host
}

# Line the tags up past the steps we can predict, within the terminal width
foreach label [list "Connecting to $target_label" "Proxy jump via $jump_via" "Authenticating $login_user@$target_host"] {
    set line_width [expr {max($line_width, [string length $label] + 16)}]
}
if {![catch {exec stty size < /dev/tty} size] && [lindex $size 1] > 20} {
    set line_width [expr {min($line_width, [lindex $size 1])}]
}

# ==== EVENTS ====
# Handlers for what the server sends, called from the expect loop below. Each
# finishes the step that was waiting and starts the next one. Per-connection
# state (reset on each attempt):
#   target_up      the target has answered, so its "Connecting to" step is done
#   auth_id        the login ("user@host") we last sent a password to
#   auth_who       how the steps name that login
#   auth_streak    prompts in a row for that login
#   tried          passwords already sent to that login
#   sent_password  the last one sent
#   expiry_notice  the server said the password has expired
#   expiry_shown   the "Password expired" step has been shown
#   change_stage   how far a forced change has got: current, new, confirm, done
#   change_tries   new passwords sent so far

# The target answered, so everything in front of it worked
proc target_reached {} {
    global target_up step_kind target_label
    set shown [expr {$target_up || $step_kind eq "connect"}]
    step_done OK
    if {!$shown} {
        step_line "Connecting to $target_label" OK
    }
    set target_up 1
}

# Whether a login prompt's "user@host" (or bare host) is for the target rather
# than a jump host. Prompts that don't say are only assumed to be the target
# when there is no jump.
proc is_target {id} {
    global target_names jump_via
    if {$id eq ""} {
        return [expr {$jump_via eq ""}]
    }
    return [expr {[string tolower [regsub {^.*@} $id ""]] in $target_names}]
}

# The "user@host" a login prompt is for: "bob@host's password: " (password
# auth) or "(bob@host) Password: " (keyboard-interactive, OpenSSH 8.4+)
proc prompt_identity {line} {
    if {[regexp {^\((\S+@\S+)\)} $line -> id] || [regexp {(\S+@\S+)'s password} $line -> id]} {
        return $id
    }
    return ""
}

# How steps name a login: the target and a lone jump host by the names the
# user knows them by (an ssh_config alias may resolve to an IP), anything else
# by what its prompt says
proc login_label {id} {
    global login_user target_label jump_host
    set user $login_user
    regexp {^([^@]+)@} $id -> user
    if {[is_target $id]} {
        set host $target_label
    } elseif {$id ne "" && $jump_host ne ""} {
        set host $jump_host
    } else {
        return $id
    }
    return [expr {$user eq "" ? $host : "$user@$host"}]
}

# $pw got login $id through: offer it there first next time, and to other
# logins before asking the user
proc password_worked {id pw} {
    global login_password known_passwords
    set login_password($id) $pw
    set known_passwords [linsert [lsearch -all -inline -not -exact $known_passwords $pw] 0 $pw]
}

# Answer a login prompt for $id. A login gets the password that last worked
# for it (the target: the saved one), then any other that has worked this run
# (a jump host may or may not share the target's), and only then is the user
# asked. Another prompt for the login we just answered means the password was
# rejected. Prompts that don't name their host can't be told apart from the
# next hop's, so with a jump only the third in a row counts.
proc answer_login {id denied} {
    global step_kind auth_id auth_who auth_streak tried sent_password jump_via cached_password
    global known_passwords login_password vault_password vault_password_used vault_password_failed
    global new_password YELLOW DIM

    if {$id eq $auth_id} {
        incr auth_streak
    } else {
        set auth_streak 1
    }
    set again [expr {$id eq $auth_id && ($id ne "" || $jump_via eq "" || $auth_streak > 2)}]
    set retry [expr {$step_kind eq "auth" && ($denied || $again)}]
    if {$retry} {
        step_done FAIL
        if {$vault_password_used && !$vault_password_failed && $sent_password eq $vault_password && [is_target $id]} {
            # Saved password rejected, ask the user
            set vault_password_failed 1
            say "Saved password was rejected." $YELLOW
        }
        set auth_streak 1
    } else {
        set tried {}
        if {[is_target $id]} {
            target_reached
        } else {
            step_done OK
        }
    }

    set who [login_label $id]
    set auth_who $who
    set candidates $known_passwords
    if {[is_target $id] && $cached_password ne ""} {
        set candidates [linsert $candidates 0 $cached_password]
    }
    if {[info exists login_password($id)]} {
        set candidates [linsert $candidates 0 $login_password($id)]
    }
    set password ""
    foreach pw $candidates {
        if {$pw ni $tried} {
            set password $pw
            break
        }
    }
    if {$password ne "" && $retry} {
        say [expr {$password eq $new_password ? "Trying your new password." : "Trying another password from this session."}] $DIM
    } elseif {$password eq ""} {
        set password [read_password [expr {$who eq "" ? "Password" : "Password for $who"}]]
        # Debug (uncomment to trace user-typed password):
        # set _sum 0; foreach _c [split $password ""] { scan $_c %c _code; incr _sum $_code }
        # puts "\[DEBUG\] user typed: len=[string length $password] sum=$_sum"
    }
    lappend tried $password
    step [expr {$who eq "" ? "Authenticating" : "Authenticating $who"}] auth
    set auth_id $id
    set sent_password $password
    send -- "$password\r"
}

# A forced password change: the login itself went through. Shown once per
# connection, though a keyboard-interactive server (IPA) starts the login
# over after refusing a new password.
proc password_expired {} {
    global step_kind expiry_shown
    if {$step_kind eq "auth"} {
        step_done OK
    }
    if {!$expiry_shown} {
        set expiry_shown 1
        step_line "Password expired" WARN
    }
}

# The server refused the new password: show its reason. The old password
# still stands.
proc change_refused {before} {
    global change_stage RED
    step_done FAIL
    set reason [server_lines $before]
    if {$reason eq ""} {
        set reason [list "The new password was not accepted."]
    }
    foreach line $reason {
        say $line $RED
    }
    set change_stage ""
}

# "Current password:" - the one we just logged in with, unless it was already
# turned down here
proc send_current_password {} {
    global change_stage sent_password RED
    password_expired
    if {$change_stage eq "current"} {
        say "Current password was rejected." $RED
        set sent_password ""
    }
    if {$sent_password eq ""} {
        set sent_password [read_password "Current password"]
    }
    set change_stage current
    send -- "$sent_password\r"
}

# "New password:" - have the user pick one, confirmed locally so a typo
# doesn't use up the server's retries. Being asked again after we've sent one
# means the server refused it (pam_pwquality re-prompts), so show its reason.
proc choose_new_password {before} {
    global change_stage change_tries new_password auth_who YELLOW DIM
    password_expired
    if {$change_stage in {new confirm}} {
        change_refused $before
    } elseif {$change_tries == 0} {
        say [expr {$auth_who eq "" ? "Choose a new password." : "Choose a new password for $auth_who."}] $DIM
    }
    incr change_tries
    while {1} {
        set new_password [read_password "New password"]
        if {$new_password eq ""} {
            say "Password can't be empty." $YELLOW
        } elseif {[read_password "Confirm new password"] ne $new_password} {
            say "Passwords don't match, try again." $YELLOW
        } else {
            break
        }
    }
    step "Changing password" change
    set change_stage new
    send -- "$new_password\r"
}

# "Retype new password:" - repeat the one the user already confirmed
proc confirm_new_password {} {
    global change_stage new_password
    if {$new_password eq ""} {
        set new_password [read_password "Confirm new password"]
    }
    set change_stage confirm
    send -- "$new_password\r"
}

# The server took the new password: log in with it from here on
proc password_change_accepted {} {
    global change_stage password_changed cached_password new_password step_kind auth_id
    if {$step_kind eq "change"} {
        step_done OK
    } else {
        step_line "Changing password" OK
    }
    set change_stage done
    set password_changed 1
    set cached_password $new_password
    password_worked $auth_id $new_password
}

# Any prompt ending in "...password...:" - work out which kind it is. The
# "user@host" part is dropped first so a host named e.g. "newbox" can't look
# like "New password:". A bare "Password:" right after an expiry notice is the
# server asking for the current password.
proc answer_password_prompt {line before} {
    global expiry_notice change_stage step_kind auth_id
    set kind [string tolower $line]
    regsub {^\(\S+@\S+\)\s*} $kind "" kind
    regsub {\S+@\S+'s\s+} $kind "" kind
    if {[regexp {\m(retype|re-type|reenter|re-enter|repeat|again|confirm|verify)\M} $kind]} {
        confirm_new_password
    } elseif {[regexp {\mnew\M} $kind]} {
        choose_new_password $before
    } elseif {[regexp {\m(current|old)\M} $kind] || ($expiry_notice && $change_stage eq "" && $step_kind eq "auth")} {
        send_current_password
    } else {
        set id [prompt_identity $line]
        if {$change_stage in {new confirm}} {
            if {$id eq $auth_id} {
                # Back at the same login mid-change: the new password was
                # refused and the server started the login over (IPA does
                # this with keyboard-interactive)
                change_refused $before
            } else {
                # On to the next hop, so the login being changed went through
                # (a jump host's change never reaches a shell to show it)
                password_change_accepted
            }
        }
        answer_login $id [string match "*Permission denied*" $before]
    }
}

# Track if we successfully reached a shell
set reached_shell 0

# Suppress banner/MOTD output
log_user 0

# ==== START SESSION ====
# Runs once, plus a reconnect if the server signs us out after a forced
# password change, or hangs up on a refused new password and the user wants
# another go.
set attempt 0
set relogged 0
while {1} {
    incr attempt
    set target_up 0
    set auth_id ""
    set auth_who ""
    set auth_streak 0
    set tried {}
    set sent_password ""
    set expiry_notice 0
    set expiry_shown 0
    set expiry_warned 0
    set change_stage ""
    set change_tries 0
    set reconnect 0

    set verb [expr {$attempt == 1 ? "Connecting to" : "Reconnecting to"}]
    set mode [expr {$proto eq "sftp" ? " via ${YELLOW}SFTP$RESET" : ""}]
    puts "\n$GREEN\[VIPERSSH\]$RESET $verb $CYAN$dest$RESET$mode\n"
    if {$jump_via ne ""} {
        step "Proxy jump via $jump_via" route
    } else {
        step "Connecting to $target_label" connect
    }

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
        -re {\(yes/no[^)]*\)\? ?$} {
            # Unknown host key - accept it (trust on first use)
            set host $target_label
            regexp {authenticity of host '([^' ]+)} $expect_out(buffer) -> host
            regsub {^\[(.*)\]:[0-9]+$} $host {\1} host
            if {$change_stage in {new confirm}} {
                # On to the next hop, so a jump host's change went through
                password_change_accepted
            }
            if {[is_target $host]} {
                target_reached
            } else {
                step_done OK
            }
            step_line "Accepting new host key for [regsub {^.*@} [login_label $host] ""]" OK
            send "yes\r"
            exp_continue
        }

        -nocase -re {password (has )?expired|required to change your password|password change required} {
            set expiry_notice 1
            exp_continue
        }

        -nocase -re {password will expire in ([0-9]+) day} {
            if {!$expiry_warned} {
                set expiry_warned 1
                set days $expect_out(1,string)
                step_done OK
                step_line "Password expires in $days [expr {$days == 1 ? "day" : "days"}]" WARN
            }
            exp_continue
        }

        -nocase -re {tokens updated successfully|password updated successfully|password (has been |was )?changed|password change successful} {
            if {$change_stage in {new confirm}} {
                password_change_accepted
            }
            exp_continue
        }

        -nocase -re {[^\r\n]*password[^\r\n]*:\s*$} {
            set line $expect_out(0,string)
            answer_password_prompt $line [string range $expect_out(buffer) 0 end-[string length $line]]
            exp_continue
        }

        eof {
            set before [expr {[info exists expect_out(buffer)] ? $expect_out(buffer) : ""}]
            if {$password_changed && !$relogged} {
                # Servers sign you out after a forced change; log back in with it
                set relogged 1
                set reconnect 1
                catch {wait -nowait}
            } elseif {$change_stage in {new confirm}} {
                # The server refused the new password and hung up (IPA with
                # password auth, or passwd out of retries). The old password
                # still works, so offer another go.
                change_refused $before
                if {![ask_yes "    Try another password? (y/n) "]} {
                    exit 0
                }
                set reconnect 1
                catch {wait -nowait}
            } else {
                if {$step_open} {
                    step_done FAIL
                } else {
                    step_line "Connection closed" FAIL
                }
                # Show what ssh said, since we never reached the shell
                foreach line [server_lines $before] {
                    say $line
                }
                exit 0
            }
        }

        # Shell prompt detection - re-enable output and hand off
        -re {[$#%>] $} {
            if {$change_stage in {new confirm}} {
                # Keyboard-interactive changes happen inside the login itself
                password_change_accepted
            } elseif {$step_kind eq "auth"} {
                # The login that got us here is the target's
                set cached_password $sent_password
            }
            target_reached
            set reached_shell 1
            log_user 1
            send "\r"
        }
    }

    if {!$reconnect} {
        break
    }
}

# Determine exit code based on vault usage. The saved password is stale if the
# target ended up taking another one (it was rejected, or changed).
if {$vault_password_used && $cached_password ne $vault_password} {
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
        set prompt_msg "\n$MAGENTA\[VAULT\]$RESET Save password? (y/n) "
    } elseif {$viper_exit == 12} {
        # Vault password failed or was changed, user has a new one
        set should_prompt 1
        set prompt_msg "\n$MAGENTA\[VAULT\]$RESET Update saved password? (y/n) "
    }

    if {$should_prompt} {
        if {[ask_yes $prompt_msg]} {
            # Debug (uncomment to trace pipe write):
            # set _sum 0; foreach _c [split $cached_password ""] { scan $_c %c _code; incr _sum $_code }
            # puts "\[DEBUG\] writing to pipe: len=[string length $cached_password] sum=$_sum"
            if {[catch {
                set chan [open "/dev/fd/$pw_fd" w]
                puts -nonewline $chan $cached_password
                close $chan
            } err]} {
                puts "$MAGENTA\[VAULT\]$RESET Failed to save: $err"
            } else {
                puts "$MAGENTA\[VAULT\]$RESET Saved."
            }
        }
    }

    unset -nocomplain env(VIPER_PW_FD)
}

# Clear passwords from memory before interactive mode
set cached_password ""
set new_password ""
set sent_password ""
set vault_password ""
set known_passwords {}
array unset login_password

puts -nonewline "\033]0;$dest\007"
flush stdout

# Note why the session ends from ssh's (or the remote shell's) last words.
# Output still reaches the user as it arrives; a reason only counts if the
# session ends right after it, so the same words in ordinary output don't.
set disconnect_reason ""
set disconnect_at 0
interact {
    -timeout 60 {
        send " \b"
    }
    -o
    -nobuffer -re {timed out waiting for input|auto-logout} {
        set disconnect_reason idle
        set disconnect_at [clock milliseconds]
    }
    -nobuffer -re {closed by remote host} {
        set disconnect_reason closed
        set disconnect_at [clock milliseconds]
    }
    -nobuffer -re {Timeout, server [^\r\n]* not responding} {
        set disconnect_reason timeout
        set disconnect_at [clock milliseconds]
    }
    -nobuffer -re {Broken pipe|Connection reset by peer|Connection timed out|Operation timed out} {
        set disconnect_reason dropped
        set disconnect_at [clock milliseconds]
    }
}

# ==== DISCONNECT ====
# Closing line to match the opening one
if {[clock milliseconds] - $disconnect_at > 3000} {
    set disconnect_reason ""
}
switch -- $disconnect_reason {
    idle    { set color $YELLOW; set line "Disconnected from $CYAN$dest$RESET: ${YELLOW}logged out for inactivity" }
    closed  { set color $YELLOW; set line "Disconnected from $CYAN$dest$RESET: ${YELLOW}closed by the server" }
    timeout { set color $RED; set line "Lost connection to $CYAN$dest$RESET: ${RED}the server stopped responding" }
    dropped { set color $RED; set line "Lost connection to $CYAN$dest$RESET: ${RED}network error" }
    default { set color $GREEN; set line "Disconnected from $CYAN$dest$RESET" }
}
catch {puts "\n$color\[VIPERSSH\]$RESET $line$RESET"}

exit $viper_exit
