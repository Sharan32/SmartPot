#!/bin/sh
mkdir /var/lock
mkdir /var/run
/sbin/ubusd &
/sbin/procd &
/etc/rc.d/S00sysfixtime start
/etc/rc.d/S00urngd start
/etc/rc.d/S10boot start
/etc/rc.d/S11sysctl start
/etc/rc.d/S12log start
/etc/rc.d/S12rpcd start
/etc/rc.d/S19dropbear start
/etc/rc.d/S19wpad start
/etc/rc.d/S25packet_steering start
/etc/rc.d/S35odhcpd start
/etc/rc.d/S50cron start
/etc/rc.d/S50uhttpd start
/bin/ash
