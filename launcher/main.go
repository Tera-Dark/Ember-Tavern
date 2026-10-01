package main

import (
	"context"
	"embed"
	"ember-tavern/launcher/internal/engine"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"runtime"
	"sync"
	"syscall"
	"time"
)

//go:embed ui/*
var assets embed.FS

func platformName() string { return runtime.GOOS + " / " + runtime.GOARCH }
func defaultRoot() string {
	if runtime.GOOS == "windows" {
		return filepath.Join(os.Getenv("LOCALAPPDATA"), "EmberTavern")
	}
	base, _ := os.UserConfigDir()
	return filepath.Join(base, "ember-tavern")
}
func main() {
	root := flag.String("data-dir", defaultRoot(), "Launcher data directory")
	listen := flag.String("listen", "127.0.0.1:0", "Local UI listen address")
	preview := flag.Bool("preview", false, "Development-only proxied UI; no desktop integration")
	headless := flag.Bool("headless", false, "Serve local UI without window")
	python := flag.String("dev-python", "", "Development Python override")
	source := flag.String("dev-source", "", "Development local source snapshot")
	skip := flag.Bool("dev-skip-deps", false, "Testing only: skip requirements install")
	system := flag.Bool("dev-system-packages", false, "Testing only: venv can use system packages")
	bundled := flag.String("bundled-source", "", "Trusted host files shipped with desktop")
	commit := flag.String("bundled-commit", "", "Bundled host commit")
	desktop := flag.Bool("desktop-control", false, "Private stdio handshake for Electron main process")
	flag.Parse()
	if !*preview {
		host, _, e := net.SplitHostPort(*listen)
		if e != nil || host != "127.0.0.1" {
			fmt.Fprintln(os.Stderr, "生产启动器仅允许监听 127.0.0.1")
			os.Exit(2)
		}
	}
	if e := os.MkdirAll(*root, 0700); e != nil {
		log.Fatal(e)
	}
	logFile, e := os.OpenFile(filepath.Join(*root, "launcher.log"), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0600)
	if e != nil {
		log.Fatal(e)
	}
	defer logFile.Close()
	log.SetOutput(logFile)
	manager, e := engine.New(engine.Config{Root: *root, Python: *python, LocalSource: *source, BundledSource: *bundled, BundledCommit: *commit, SkipDependencies: *skip, SystemPackages: *system, Preview: *preview})
	if e != nil {
		log.Fatal(e)
	}
	defer manager.Close()
	listener, e := net.Listen("tcp", *listen)
	if e != nil {
		log.Fatal(e)
	}
	token := nonce()
	stop := make(chan os.Signal, 1)
	var stopOnce sync.Once
	api := &API{Manager: manager, Token: token, Preview: *preview, Open: openExternal, Shutdown: func() { stopOnce.Do(func() { stop <- syscall.SIGTERM }) }}
	server := &http.Server{Handler: api.Handler(), ReadHeaderTimeout: 10 * time.Second}
	go func() { _ = server.Serve(listener) }()
	url := "http://" + listener.Addr().String() + "/bootstrap?key=" + token
	if *preview {
		url = "http://" + listener.Addr().String() + "/"
	}
	if *desktop {
		_ = json.NewEncoder(os.Stdout).Encode(map[string]any{"ready": true, "port": listener.Addr().(*net.TCPAddr).Port, "token": token})
	} else {
		fmt.Println("余烬启动器 " + engine.LauncherVersion + " · UI " + listener.Addr().String())
	}
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)
	done := make(chan struct{})
	finished := make(chan struct{})
	go func() {
		select {
		case <-stop:
		case <-done:
		}
		manager.Close()
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		_ = server.Shutdown(ctx)
		close(finished)
	}()
	if *headless || *preview {
		<-finished
	} else {
		runWindow(url, filepath.Join(*root, "webview"))
		close(done)
		<-finished
	}
}
