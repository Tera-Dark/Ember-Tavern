//go:build windows

package engine

import (
	"context"
	"net"
	"strconv"
	"syscall"
)

func listenPort(port int) (net.Listener, error) {
	// Winsock's default wildcard bind can overlap a specific-address listener.
	// Match Python's exclusive bind, before bind(), for a truthful availability check.
	config := net.ListenConfig{Control: func(_, _ string, raw syscall.RawConn) error {
		var optionError error
		if e := raw.Control(func(socket uintptr) {
			optionError = syscall.SetsockoptInt(syscall.Handle(socket), syscall.SOL_SOCKET, ^syscall.SO_REUSEADDR, 1)
		}); e != nil {
			return e
		}
		return optionError
	}}
	return config.Listen(context.Background(), "tcp4", "0.0.0.0:"+strconv.Itoa(port))
}
