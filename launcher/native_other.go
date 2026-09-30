//go:build !windows

package main

import (
	"os"
	"os/exec"
	"os/signal"
	"runtime"
)

func openExternal(target string) error {
	cmd := "xdg-open"
	if runtime.GOOS == "darwin" {
		cmd = "open"
	}
	return exec.Command(cmd, target).Start()
}
func runWindow(url, path string) {
	_ = openExternal(url)
	c := make(chan os.Signal, 1)
	signal.Notify(c, os.Interrupt)
	<-c
}
