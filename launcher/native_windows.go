//go:build windows

package main

import (
	webview2 "github.com/jchv/go-webview2"
	"github.com/jchv/go-webview2/webviewloader"
	"golang.org/x/sys/windows"
	"log"
	"os/exec"
	"runtime"
	"syscall"
	"unsafe"
)

func openExternal(target string) error {
	c := exec.Command("rundll32.exe", "url.dll,FileProtocolHandler", target)
	c.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	return c.Start()
}
func runWindow(url, path string) {
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()
	version, e := webviewloader.GetInstalledVersion()
	if e != nil || version == "" {
		log.Println("WebView2 不可用，自动使用系统浏览器")
		_ = openExternal(url)
		user32 := windows.NewLazySystemDLL("user32.dll")
		text, _ := windows.UTF16PtrFromString("启动器已在浏览器打开。浏览器页面关闭不会结束启动器；点击此窗口确定后关闭并停止实例。建议安装 Microsoft WebView2 获得完整桌面窗口。")
		title, _ := windows.UTF16PtrFromString("余烬启动器")
		user32.NewProc("MessageBoxW").Call(0, uintptr(unsafe.Pointer(text)), uintptr(unsafe.Pointer(title)), 0)
		return
	}
	w := webview2.NewWithOptions(webview2.WebViewOptions{Debug: false, DataPath: path, AutoFocus: true, WindowOptions: webview2.WindowOptions{Title: "余烬启动器 · 0.1.0 测试版", Width: 1360, Height: 900, Center: true, IconId: 2}})
	if w == nil {
		_ = openExternal(url)
		return
	}
	defer w.Destroy()
	enabled := uint32(1)
	hwnd := uintptr(w.Window())
	windows.NewLazySystemDLL("dwmapi.dll").NewProc("DwmSetWindowAttribute").Call(hwnd, 20, uintptr(unsafe.Pointer(&enabled)), 4)
	w.SetSize(980, 680, webview2.HintMin)
	w.Navigate(url)
	w.Run()
}
