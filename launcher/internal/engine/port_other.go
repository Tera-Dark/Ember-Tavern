//go:build !windows

package engine

import (
	"net"
	"strconv"
)

func listenPort(port int) (net.Listener, error) {
	return net.Listen("tcp4", "0.0.0.0:"+strconv.Itoa(port))
}
