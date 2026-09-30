//go:build windows

package engine

import (
	"errors"
	"golang.org/x/sys/windows"
	"os"
)

func acquireLock(path string) (*os.File, error) {
	p, e := windows.UTF16PtrFromString(path)
	if e != nil {
		return nil, e
	}
	h, e := windows.CreateFile(p, windows.GENERIC_READ|windows.GENERIC_WRITE, 0, nil, windows.OPEN_ALWAYS, windows.FILE_ATTRIBUTE_NORMAL, 0)
	if e != nil {
		return nil, errors.New("这个数据目录已有启动器运行，请打开现有窗口")
	}
	return os.NewFile(uintptr(h), path), nil
}
