#!/bin/sh
# Start sshd with bob's password in $PASSWORD_STATE (default ok)
password-state "${PASSWORD_STATE:-ok}"
mkdir -p /run/sshd
exec /usr/sbin/sshd -D -e $SSHD_OPTS
