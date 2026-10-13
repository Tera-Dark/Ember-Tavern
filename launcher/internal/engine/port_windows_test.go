//go:build windows

package engine

import (
	"syscall"
	"testing"
)

func TestWindowsPortCheckRejectsBoundSocketBeforeListen(t *testing.T) {
	port := freeTestPort(t)
	socket, e := syscall.Socket(syscall.AF_INET, syscall.SOCK_STREAM, syscall.IPPROTO_TCP)
	if e != nil {
		t.Fatal(e)
	}
	defer syscall.Closesocket(socket)
	if e = syscall.SetsockoptInt(socket, syscall.SOL_SOCKET, syscall.SO_REUSEADDR, 1); e != nil {
		t.Fatal(e)
	}
	if e = syscall.Bind(socket, &syscall.SockaddrInet4{Port: port}); e != nil {
		t.Fatal(e)
	}
	if availablePort(port) == nil {
		t.Fatal("a wildcard socket reserved before listen was reported free")
	}
}
